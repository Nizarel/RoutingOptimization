"""Allow ``python -m src`` to start the MCP server.

Importing :mod:`src.server` here (rather than executing it as ``__main__``)
guarantees a single canonical module so all ``@mcp.tool()`` decorators in
``src.tools.*`` register against the same FastMCP instance.
"""
from src.server import main

if __name__ == "__main__":
    main()
