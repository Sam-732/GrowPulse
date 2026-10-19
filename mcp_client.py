"""Phase 6: connect to the n8n MCP server and list tools. Must find exactly 3, none that can send."""
import asyncio
import sys

from src.mcp_tools import EXPECTED_TOOLS, McpConfigError, open_session


async def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        async with open_session() as s:
            tools = (await s.list_tools()).tools
    except McpConfigError as e:
        print(f"FAIL: {e}")
        return 1
    names = sorted(t.name for t in tools)
    for t in tools:
        print(f"- {t.name}: {(t.description or '').strip()[:90]}")
    checks = {
        "exactly 3 tools": len(tools) == 3,
        f"names == {sorted(EXPECTED_TOOLS)}": set(names) == EXPECTED_TOOLS,
        "no tool name contains 'send'": not any("send" in n.lower() for n in names),
    }
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
