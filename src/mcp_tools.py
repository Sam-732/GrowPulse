"""Shared MCP connection helper for mcp_client.py and approve.py (n8n MCP Server Trigger, Bearer auth)."""
import contextlib
import os

import truststore
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

truststore.inject_into_ssl()
load_dotenv()

EXPECTED_TOOLS = {"append_to_doc", "read_doc", "create_email_draft"}


class McpConfigError(RuntimeError):
    """One-sentence, user-facing problem (technical detail goes to the log file)."""


def config() -> tuple[str, str]:
    url, token = os.getenv("N8N_MCP_URL", "").strip(), os.getenv("N8N_MCP_TOKEN", "").strip()
    if not url or not token:
        raise McpConfigError("N8N_MCP_URL and N8N_MCP_TOKEN are not set in .env yet (see docs/n8n_setup.md).")
    return url, token


@contextlib.asynccontextmanager
async def open_session():
    """Yield an initialised ClientSession. n8n's MCP Server Trigger speaks SSE; streamable HTTP is the fallback."""
    url, token = config()
    headers = {"Authorization": f"Bearer {token}"}
    last: Exception | None = None
    stack = session = None
    for kind in ("sse", "streamable"):
        attempt = contextlib.AsyncExitStack()
        try:
            if kind == "streamable":
                http = await attempt.enter_async_context(create_mcp_http_client(headers=headers))
                streams = await attempt.enter_async_context(streamable_http_client(url, http_client=http))
            else:
                streams = await attempt.enter_async_context(sse_client(url, headers=headers))
            session = await attempt.enter_async_context(ClientSession(streams[0], streams[1]))
            await session.initialize()
            stack = attempt
            break
        except BaseException as e:          # noqa: BLE001 - setup only; try the other transport
            last = e
            with contextlib.suppress(BaseException):
                await attempt.aclose()
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
    if session is None:
        raise McpConfigError(
            "Could not connect to the n8n MCP URL. Check that the workflow is Published, the URL is the "
            f"Production URL, and the Bearer token matches. ({type(last).__name__})") from last
    try:
        yield session
    finally:
        with contextlib.suppress(BaseException):
            await stack.aclose()


def text_of(result) -> str:
    """Join the text parts of an MCP tool result."""
    return "\n".join(getattr(c, "text", "") for c in result.content)
