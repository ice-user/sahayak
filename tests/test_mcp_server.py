"""Starts the real MCP server over stdio and calls its tools like a client would."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


async def _run():
    params = StdioServerParameters(command=sys.executable, args=["-m", "sahayak.mcp_server"], cwd=str(ROOT),
                                    env={**os.environ, "SAHAYAK_SEARCH": "bm25"})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            res = await session.call_tool("check_eligibility", {"profile": {"age": 75}})
            return tools, json.loads(res.content[0].text)


def test_mcp_server_end_to_end():
    tools, result = asyncio.run(_run())
    assert tools == {"search_schemes", "get_scheme_details", "check_eligibility"}
    assert "pmjay_senior" in {r["scheme_id"] for r in result["eligible"]}
