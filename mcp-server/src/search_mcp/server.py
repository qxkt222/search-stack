"""MCP server bootstrap and tool discovery."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from mcp.server.mcpserver import MCPServer

import search_mcp.tools as tools_package

mcp = MCPServer(
    "search-mcp",
    version="0.1.0",
    instructions=(
        "Search the web through a SearXNG instance and extract readable text "
        "from result pages. All tools return an {ok, result} or {ok, error} "
        "envelope and never raise."
    ),
)


def discover_tools() -> list[str]:
    """Import every ``search_mcp.tools`` module and call its ``register``."""

    registered: list[str] = []
    for module_info in pkgutil.iter_modules(tools_package.__path__):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"search_mcp.tools.{module_info.name}")
        register = getattr(module, "register", None)
        if callable(register):
            register(mcp)
            registered.append(module_info.name)
    return registered


discover_tools()


def main() -> None:
    """Run the server over stdio (the transport used by MCP hosts)."""

    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
