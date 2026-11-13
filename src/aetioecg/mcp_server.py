import base64
import json
from typing import Any, Literal

import anyio
from google.protobuf.json_format import MessageToDict, ParseDict
from mcp.server.mcpserver import MCPServer
from mcp_types import BlobResourceContents, CallToolResult, EmbeddedResource, TextContent

from aetioecg.core import EcgSource, get_ecg, list_options
from aetioecg.v1.ecg_pb2 import EcgRequest

OPTIONS_DESCRIPTION = """\
List every SCP-ECG statement code get_ecg accepts, with its description and kind (diagnostic, form, rhythm).
Returns aetioecg.v1.EcgOptions in proto3 JSON."""

GET_DESCRIPTION = """\
Get one real-looking 12-lead ECG that shows all requested SCP-ECG statements, as an SVG on grid paper (25 mm/s, 10 mm/mV).
statements: codes from list_ecg_options, e.g. ["AFIB"], ["IMI"] or ["NORM"] for a normal ECG.
sex and age are preferences, not filters. The same arguments and seed return the same ECG.
Returns the SVG as an embedded resource and aetioecg.v1.Ecg without the image (actual statements, sex, age, seed, attribution)
in proto3 JSON as structured content. The ECG may show further statements than requested; they are all listed."""


def build_server(source: EcgSource) -> MCPServer:
    server = MCPServer("aetioecg", instructions="Provides 12-lead ECGs by SCP-ECG statement. Call list_ecg_options first.")

    @server.tool(description=OPTIONS_DESCRIPTION)
    async def list_ecg_options() -> CallToolResult:
        options = MessageToDict(await anyio.to_thread.run_sync(list_options, source))
        return CallToolResult(content=[TextContent(text=json.dumps(options))], structured_content=options)

    # The parameters mirror aetioecg.v1.EcgRequest field by field (a test enforces it).
    @server.tool(description=GET_DESCRIPTION)
    async def get_ecg_svg(
        statements: list[str],
        sex: Literal["SEX_UNSPECIFIED", "SEX_MALE", "SEX_FEMALE"] = "SEX_UNSPECIFIED",
        age: int | None = None,
        seed: int | None = None,
    ) -> CallToolResult:
        fields: dict[str, Any] = {"statements": statements, "sex": sex, "age": age, "seed": seed}
        request = ParseDict({k: v for k, v in fields.items() if v is not None}, EcgRequest())
        ecg = await anyio.to_thread.run_sync(get_ecg, source, request)
        svg = BlobResourceContents(
            uri=f"ecg://{ecg.attribution.record}.svg", mime_type=ecg.mime_type, blob=base64.b64encode(ecg.image).decode()
        )
        ecg.ClearField("image")
        return CallToolResult(content=[EmbeddedResource(resource=svg)], structured_content=MessageToDict(ecg))

    return server
