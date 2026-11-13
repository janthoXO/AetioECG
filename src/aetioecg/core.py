"""The whole core: the `EcgSource` port and the two contract endpoints, `list_options` and `get_ecg`.

CLI and MCP are driving adapters over these two functions; PTB-XL retrieval (`ptbxl.py`) is one
driven adapter behind `EcgSource`. A parametric synthesizer would be a second one: it only has to
produce a `Recording`, rendering and validation stay here.
"""

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from aetioecg.render import render_svg
from aetioecg.v1.ecg_pb2 import Attribution, Ecg, EcgOptions, EcgRequest

LEADS = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")


@dataclass(frozen=True)
class Recording:
    """A 12-lead ECG as a source produces it, before rendering."""

    leads: Mapping[str, Sequence[float]]  # every name in LEADS -> samples in mV
    rate: int  # samples per second
    statements: list[str]  # SCP-ECG codes the recording shows, all listed in the source's options
    sex: int  # Sex enum value
    age: int | None
    attribution: Attribution


class EcgSource(Protocol):
    def options(self) -> EcgOptions:
        """Every statement `retrieve` can be asked for."""
        ...

    def retrieve(self, request: EcgRequest, rng: random.Random) -> Recording:
        """A recording showing every statement in `request.statements` (already validated); all randomness from `rng`.
        Raises ValueError when no recording fits."""
        ...


def list_options(source: EcgSource) -> EcgOptions:
    return source.options()


def get_ecg(source: EcgSource, request: EcgRequest) -> Ecg:
    """Validate the request against the source's options, retrieve a recording and render it as SVG.
    Same request and seed give the same ECG."""
    known = {s.code: s for s in source.options().statements}
    if not request.statements:
        raise ValueError("statements: give at least one SCP-ECG code, e.g. NORM")
    unknown = [code for code in request.statements if code not in known]
    if unknown:
        raise ValueError(f"unknown statements {unknown}; list_options names every valid code")
    seed = request.seed if request.HasField("seed") else random.randrange(2**32)
    rec = source.retrieve(request, random.Random(seed))
    return Ecg(
        mime_type="image/svg+xml",
        image=render_svg(rec.leads, rec.rate),
        statements=[known[code] for code in rec.statements],
        sex=rec.sex,  # pyright: ignore[reportArgumentType]  # protobuf enums are ints at runtime
        age=rec.age,
        seed=seed,
        attribution=rec.attribution,
    )
