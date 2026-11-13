"""`EcgSource` over PTB-XL (21,799 real 10 s 12-lead ECGs, PhysioNet, CC BY 4.0): retrieval, not synthesis.

`base` is a local copy of the dataset or its PhysioNet URL; the same relative paths are read from either.
Only the two CSV indexes (~7 MB) are read up front, each record (120 KB at 500 Hz) on request.
"""

import ast
import csv
import io
import random
import sys
from array import array
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from urllib.request import urlopen

from aetioecg.core import Recording
from aetioecg.v1.ecg_pb2 import Attribution, EcgOptions, EcgRequest, Sex, Statement, StatementKind

PHYSIONET = "https://physionet.org/files/ptb-xl/1.0.3/"
CITATION = (
    "Wagner, P., Strodthoff, N., Bousseljot, R., Samek, W., & Schaeffter, T. (2022). PTB-XL, a large publicly available "
    "electrocardiography dataset (version 1.0.3). PhysioNet. https://doi.org/10.13026/kfzx-aw45"
)
LICENSE = "CC BY 4.0"
MIN_LIKELIHOOD = 50  # diagnostic statements below this are "unlikely" and ignored; 0 means "not rated" (form, rhythm)
BASELINE = frozenset({"SR"})  # sinus rhythm is not an unwanted extra finding
NOISE = ("baseline_drift", "static_noise", "burst_noise", "electrodes_problems")
KINDS = {
    "diagnostic": StatementKind.STATEMENT_KIND_DIAGNOSTIC,
    "form": StatementKind.STATEMENT_KIND_FORM,
    "rhythm": StatementKind.STATEMENT_KIND_RHYTHM,
}
LEAD_NAMES = {"AVR": "aVR", "AVL": "aVL", "AVF": "aVF"}


@dataclass(frozen=True)
class _Record:
    ecg_id: int
    path: str  # 500 Hz record, without extension
    codes: frozenset[str]
    sex: int  # Sex enum value
    age: int | None
    flaws: int  # noise annotations, plus 1 when not validated by a human


class PtbXl:
    def __init__(self, base: str = PHYSIONET):
        self.base = base if base.endswith("/") else base + "/"

    def _read(self, rel: str) -> bytes:
        if self.base.startswith(("http://", "https://")):
            with urlopen(self.base + rel, timeout=60) as response:
                return response.read()
        return (Path(self.base) / rel).read_bytes()

    def _csv(self, rel: str) -> list[dict[str, str]]:
        return list(csv.DictReader(io.StringIO(self._read(rel).decode())))

    @cached_property
    def _records(self) -> list[_Record]:
        records = []
        for row in self._csv("ptbxl_database.csv"):
            likelihoods: dict[str, float] = ast.literal_eval(row["scp_codes"])
            age = int(float(row["age"])) if row["age"] else None
            records.append(
                _Record(
                    ecg_id=int(row["ecg_id"]),
                    path=row["filename_hr"],
                    codes=frozenset(code for code, p in likelihoods.items() if p == 0 or p >= MIN_LIKELIHOOD),
                    sex=Sex.SEX_FEMALE if row["sex"] == "1" else Sex.SEX_MALE,
                    age=min(age, 90) if age is not None else None,  # PTB-XL codes ages over 89 as 300
                    flaws=sum(bool(row[col].strip()) for col in NOISE) + (row["validated_by_human"] != "True"),
                )
            )
        return records

    @cached_property
    def _options(self) -> EcgOptions:
        present = frozenset().union(*(r.codes for r in self._records))
        statements = [
            Statement(code=row[""], description=row["description"], kinds=[kind for col, kind in KINDS.items() if row[col]])
            for row in self._csv("scp_statements.csv")
            if row[""] in present
        ]
        return EcgOptions(source="ptb-xl", statements=statements)

    def options(self) -> EcgOptions:
        return self._options

    def retrieve(self, request: EcgRequest, rng: random.Random) -> Recording:
        wanted = frozenset(request.statements)
        age = request.age if request.HasField("age") else None

        def rank(r: _Record) -> tuple[int, int, bool, int]:
            # fewest extra findings, then cleanest signal, then the requested sex, then age within 10-year steps
            extras = len(r.codes - wanted - BASELINE)
            age_gap = abs(r.age - age) // 10 if age is not None and r.age is not None else 0
            return extras, r.flaws, bool(request.sex) and r.sex != request.sex, age_gap

        candidates = [r for r in self._records if wanted <= r.codes]
        if not candidates:
            raise ValueError(f"no PTB-XL record shows all of {sorted(wanted)}; try fewer statements")
        best = min(map(rank, candidates))
        record = rng.choice([r for r in candidates if rank(r) == best])
        leads, rate = self._signal(record.path)
        return Recording(
            leads=leads,
            rate=rate,
            statements=sorted(record.codes),
            sex=record.sex,
            age=record.age,
            attribution=Attribution(record=f"ptb-xl/{record.ecg_id}", citation=CITATION, license=LICENSE),
        )

    def _signal(self, path: str) -> tuple[dict[str, list[float]], int]:
        """WFDB format 16 (interleaved little-endian int16), the only format PTB-XL uses."""
        header = self._read(path + ".hea").decode().split("\n")
        _, count, rate, _ = header[0].split()[:4]
        n = int(count)
        raw = array("h", self._read(path + ".dat"))
        if sys.byteorder == "big":
            raw.byteswap()
        leads = {}
        for i, line in enumerate(header[1 : n + 1]):
            fields = line.split()
            if fields[1] != "16":
                raise ValueError(f"{path}: WFDB format {fields[1]}, expected 16")
            gain, _, rest = fields[2].split("/")[0].partition("(")  # "1000.0(0)/mV": gain(baseline)/unit
            baseline = int(rest.split(")")[0]) if rest else 0
            leads[LEAD_NAMES.get(fields[-1], fields[-1])] = [(v - baseline) / float(gain) for v in raw[i::n]]
        return leads, int(rate)
