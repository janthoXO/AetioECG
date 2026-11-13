import base64
import json
import random
from array import array

import pytest
from google.protobuf.json_format import MessageToDict
from mcp import Client

from aetioecg import cli
from aetioecg.core import LEADS, Recording, get_ecg
from aetioecg.mcp_server import build_server
from aetioecg.ptbxl import PtbXl
from aetioecg.v1.ecg_pb2 import Attribution, EcgOptions, EcgRequest, Sex, Statement

pytestmark = pytest.mark.anyio

N = 1000  # samples per fake record (2 s at 500 Hz)
HEADER = "ecg_id,age,sex,scp_codes,validated_by_human,baseline_drift,static_noise,burst_noise,electrodes_problems,filename_hr"
# id, age, sex (0 male, 1 female), scp_codes, validated, static_noise
RECORDS = [
    (1, 60, 0, {"AFIB": 100.0}, True, ""),
    (2, 60, 0, {"AFIB": 100.0, "IMI": 80.0}, True, ""),
    (3, 70, 1, {"AFIB": 100.0}, False, ""),  # not validated by a human
    (4, 300.0, 0, {"AFIB": 100.0, "SR": 0.0}, False, ""),  # age 300 means "over 89"
    (5, 50, 0, {"NORM": 100.0, "LAFB": 15.0}, True, ""),  # LAFB too unlikely to count
    (6, 50, 1, {"NORM": 100.0}, True, ""),
    (7, 40, 0, {"SBRAD": 100.0, "SR": 0.0}, True, ", noisy"),
    (8, 40, 0, {"SBRAD": 100.0, "IMI": 80.0}, True, ""),
]
SCP = """,description,diagnostic,form,rhythm
AFIB,atrial fibrillation,,,1.0
IMI,inferior myocardial infarction,1.0,1.0,
NORM,normal ECG,1.0,,
SR,sinus rhythm,,,1.0
SBRAD,sinus bradycardia,,,1.0
LAFB,left anterior fascicular block,1.0,,
"""
PTB_LEADS = ["I", "II", "III", "AVR", "AVL", "AVF", "V1", "V2", "V3", "V4", "V5", "V6"]


def make_ptbxl(root):
    rows = [HEADER]
    for i, age, sex, codes, validated, noise in RECORDS:
        rel = f"records500/00000/{i:05d}_hr"
        rows.append(f'{i},{age},{sex},"{codes}",{validated},,{"1" if noise else ""},,,{rel}')
        (root / "records500/00000").mkdir(parents=True, exist_ok=True)
        lines = [f"{i:05d}_hr 12 500 {N}"] + [f"{i:05d}_hr.dat 16 1000.0(0)/mV 16 0 0 0 0 {name}" for name in PTB_LEADS]
        (root / f"{rel}.hea").write_text("\n".join(lines) + "\n")
        samples = array("h", [0] * (N * 12))
        for lead in range(12):
            samples[lead] = 1000 * (lead + 1)  # sample 0 of lead i: (i + 1) mV
        (root / f"{rel}.dat").write_bytes(samples.tobytes())  # little-endian on every supported platform
    (root / "ptbxl_database.csv").write_text("\n".join(rows) + "\n")
    (root / "scp_statements.csv").write_text(SCP)
    return root


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def fake_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PTBXL_SOURCE", str(make_ptbxl(tmp_path)))
    cli.source.cache_clear()
    yield tmp_path
    cli.source.cache_clear()


@pytest.fixture
def ptbxl(fake_dir):
    return PtbXl(str(fake_dir))


def record_of(ptbxl, **request):
    return ptbxl.retrieve(EcgRequest(**request), random.Random(0)).attribution.record


def test_options_only_likely_codes_with_kinds(ptbxl):
    by_code = {s.code: s for s in ptbxl.options().statements}
    assert set(by_code) == {"AFIB", "IMI", "NORM", "SR", "SBRAD"}  # LAFB only at likelihood 15
    assert list(by_code["IMI"].kinds) == [1, 2]  # diagnostic, form
    assert list(by_code["AFIB"].kinds) == [3]  # rhythm
    assert by_code["AFIB"].description == "atrial fibrillation"


def test_signal_decodes_gain_and_lead_names(ptbxl):
    leads, rate = ptbxl._signal("records500/00000/00001_hr")
    assert rate == 500 and len(leads["I"]) == N
    assert leads["I"][0] == 1.0 and leads["aVR"][0] == 4.0 and leads["V6"][0] == 12.0
    assert set(leads) == set(LEADS)


def test_ranking_prefers_fewest_extras_then_cleanest(ptbxl):
    assert record_of(ptbxl, statements=["AFIB"]) == "ptb-xl/1"  # beats extra IMI, unvalidated and SR-only variants


def test_sinus_rhythm_is_not_an_extra(ptbxl):
    # record 7 is noisy but has no extras besides SR; record 8 is clean but carries IMI
    assert record_of(ptbxl, statements=["SBRAD"]) == "ptb-xl/7"


def test_sex_breaks_ties(ptbxl):
    assert record_of(ptbxl, statements=["NORM"], sex=Sex.SEX_FEMALE) == "ptb-xl/6"
    assert record_of(ptbxl, statements=["NORM"], sex=Sex.SEX_MALE) == "ptb-xl/5"


def test_age_over_89_is_capped(ptbxl):
    assert ptbxl._records[3].age == 90


class FakeSource:
    def options(self):
        return EcgOptions(
            source="fake",
            statements=[Statement(code="AFIB", description="atrial fibrillation"), Statement(code="IMI", description="inferior MI")],
        )

    def retrieve(self, request, rng):
        leads = {name: [rng.random()] * 100 for name in LEADS}
        return Recording(leads, 500, ["AFIB", "IMI"], Sex.SEX_MALE, 50, Attribution(record="fake/1"))


def test_get_ecg_validates_and_is_deterministic():
    src = FakeSource()
    with pytest.raises(ValueError, match="at least one"):
        get_ecg(src, EcgRequest())
    with pytest.raises(ValueError, match="unknown"):
        get_ecg(src, EcgRequest(statements=["NOPE"]))
    a, b = (get_ecg(src, EcgRequest(statements=["AFIB"], seed=7)) for _ in range(2))
    assert a.SerializeToString() == b.SerializeToString()
    assert a.mime_type == "image/svg+xml" and a.image.startswith(b"<svg")
    assert [(s.code, s.description) for s in a.statements] == [("AFIB", "atrial fibrillation"), ("IMI", "inferior MI")]


async def test_mcp_schema_matches_proto_request(ptbxl):
    async with Client(build_server(ptbxl)) as client:
        tool = next(t for t in (await client.list_tools()).tools if t.name == "get_ecg_svg")
    assert set(tool.input_schema["properties"]) == {f.json_name for f in EcgRequest.DESCRIPTOR.fields}


async def test_mcp_tools(ptbxl):
    async with Client(build_server(ptbxl)) as client:
        options = await client.call_tool("list_ecg_options", {})
        ok = await client.call_tool("get_ecg_svg", {"statements": ["AFIB"], "seed": 3})
        bad = await client.call_tool("get_ecg_svg", {"statements": ["NOPE"]})
    assert options.structured_content == MessageToDict(ptbxl.options())
    assert not ok.is_error
    resource = ok.content[0].resource
    assert resource.mime_type == "image/svg+xml" and base64.b64decode(resource.blob).startswith(b"<svg")
    assert "image" not in ok.structured_content and ok.structured_content["seed"] == 3
    assert bad.is_error


def test_cli_options_and_get(capsys, tmp_path):
    cli.main(["options"])
    assert json.loads(capsys.readouterr().out)["source"] == "ptb-xl"
    request = tmp_path / "req.json"
    request.write_text('{"statements": ["NORM"], "seed": 1}')
    out = tmp_path / "ecg.svg"
    cli.main(["get", str(request), "-o", str(out)])
    assert out.read_bytes().startswith(b"<svg")
    printed = json.loads(capsys.readouterr().out)
    assert printed["attribution"]["record"].startswith("ptb-xl/") and "image" not in printed
