import os
import sys
from functools import cache
from pathlib import Path
from typing import Any, cast

from google.protobuf.json_format import MessageToJson, Parse, ParseError
from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import CliApp, CliPositionalArg, CliSettingsSource, CliSubCommand

from aetioecg.core import EcgSource, get_ecg, list_options
from aetioecg.mcp_server import build_server
from aetioecg.ptbxl import PHYSIONET, PtbXl
from aetioecg.v1.ecg_pb2 import EcgRequest


@cache
def source() -> EcgSource:
    # ponytail: PTB-XL is the only source; pick one by an ECG_SOURCE variable once parametric synthesis exists.
    return PtbXl(os.environ.get("PTBXL_SOURCE") or PHYSIONET)


class Options(BaseModel):
    """Print every statement code `get` accepts (aetioecg.v1.EcgOptions, proto3 JSON)."""

    def cli_cmd(self) -> None:
        print(MessageToJson(list_options(source())))


class Get(BaseModel):
    """Write the ECG for an EcgRequest JSON file as SVG; print the rest of aetioecg.v1.Ecg as JSON."""

    file: CliPositionalArg[str] = Field(description="EcgRequest JSON file, '-' reads stdin")
    output: Path = Field(validation_alias=AliasChoices("o", "output"), description="SVG file to write")

    def cli_cmd(self) -> None:
        text = sys.stdin.read() if self.file == "-" else Path(self.file).read_text(encoding="utf-8")
        ecg = get_ecg(source(), Parse(text, EcgRequest()))
        self.output.write_bytes(ecg.image)
        ecg.ClearField("image")
        print(MessageToJson(ecg))
        print(f"wrote {self.output}", file=sys.stderr)


class Mcp(BaseModel):
    """Run the MCP server (stdio by default)."""

    http: bool = Field(default=False, description="Serve streamable HTTP instead of stdio")
    host: str = "127.0.0.1"
    port: int = 8000

    def cli_cmd(self) -> None:
        server = build_server(source())
        if self.http:
            server.run("streamable-http", host=self.host, port=self.port)
        else:
            server.run()


class App(BaseModel):
    """12-lead ECGs by SCP-ECG statement, rendered as SVG."""

    options: CliSubCommand[Options]
    get: CliSubCommand[Get]
    mcp: CliSubCommand[Mcp]

    def cli_cmd(self) -> None:
        CliApp.run_subcommand(self)


def main(argv: list[str] | None = None) -> None:
    try:
        # CliSettingsSource is typed for BaseSettings; plain BaseModel roots work at runtime.
        cli = CliSettingsSource(
            cast(Any, App), cli_prog_name="aetioecg", cli_kebab_case=True, cli_implicit_flags=True, cli_hide_none_type=True
        )
        CliApp.run(App, cli_args=argv, cli_settings_source=cli)
    except (ValueError, OSError, ParseError) as e:
        sys.exit(f"error: {e}")
