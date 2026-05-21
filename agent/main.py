"""Routing planner agent — FastAPI HTTP service.

Hosts a thin OpenAI tool-calling loop:
  - LLM: Azure OpenAI (Foundry) gpt-4.1 via DefaultAzureCredential.
  - Tools: dynamically discovered from the MCP server via fastmcp.Client.
  - Each model-issued tool call is dispatched back to the MCP server.

POST /chat   { "messages": [{"role":"user","content":"..."}] }
GET  /healthz
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import structlog
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from fastapi import FastAPI, HTTPException
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from openai import AsyncAzureOpenAI
from pydantic import BaseModel, Field

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env-driven; no defaults that leak into prod)
# ---------------------------------------------------------------------------
AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_OPENAI_DEPLOYMENT = os.environ["AZURE_OPENAI_DEPLOYMENT"]
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
MCP_BASE_URL = os.environ["MCP_BASE_URL"]
MCP_API_KEY = os.environ.get("MCP_API_KEY")
AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")

MAX_TOOL_ITERATIONS = int(os.environ.get("AGENT_MAX_TOOL_ITERATIONS", "8"))

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"
SYSTEM_PROMPT = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------
_credential: DefaultAzureCredential | None = None
_openai_client: AsyncAzureOpenAI | None = None
_mcp_transport: StreamableHttpTransport | None = None
_tools_cache: list[dict[str, Any]] | None = None


def _get_credential() -> DefaultAzureCredential:
    global _credential
    if _credential is None:
        kwargs: dict[str, Any] = {}
        if AZURE_CLIENT_ID:
            kwargs["managed_identity_client_id"] = AZURE_CLIENT_ID
        _credential = DefaultAzureCredential(**kwargs)
    return _credential


def _get_openai() -> AsyncAzureOpenAI:
    global _openai_client
    if _openai_client is None:
        token_provider = get_bearer_token_provider(
            _get_credential(), "https://cognitiveservices.azure.com/.default"
        )
        _openai_client = AsyncAzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_version=AZURE_OPENAI_API_VERSION,
            azure_ad_token_provider=token_provider,
        )
    return _openai_client


def _build_mcp_transport() -> StreamableHttpTransport:
    headers = {"x-api-key": MCP_API_KEY} if MCP_API_KEY else None
    return StreamableHttpTransport(MCP_BASE_URL, headers=headers)


def _get_mcp_transport() -> StreamableHttpTransport:
    global _mcp_transport
    if _mcp_transport is None:
        _mcp_transport = _build_mcp_transport()
    return _mcp_transport


async def _discover_tools() -> list[dict[str, Any]]:
    """List MCP tools and convert to OpenAI tool schema."""
    global _tools_cache
    if _tools_cache is not None:
        return _tools_cache
    async with Client(_get_mcp_transport()) as client:
        mcp_tools = await client.list_tools()
    converted: list[dict[str, Any]] = []
    for t in mcp_tools:
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema or {"type": "object", "properties": {}},
                },
            }
        )
    _tools_cache = converted
    log.info("agent.tools_discovered", count=len(converted))
    return converted


async def _call_mcp_tool(name: str, arguments: dict[str, Any]) -> str:
    async with Client(_get_mcp_transport()) as client:
        result = await client.call_tool(name, arguments)
    # result is a CallToolResult — serialize content blocks to text
    if hasattr(result, "content"):
        parts: list[str] = []
        for block in result.content:
            text = getattr(block, "text", None)
            if text is not None:
                parts.append(text)
            else:
                parts.append(json.dumps(getattr(block, "model_dump", lambda: {})()))
        return "\n".join(parts) if parts else json.dumps({"ok": True})
    return json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------
app = FastAPI(title="Routing Planner Agent", version="0.1.0")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    max_iterations: int | None = None


class ToolCallTrace(BaseModel):
    name: str
    arguments: dict[str, Any]
    result_preview: str


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCallTrace]
    iterations: int


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages must be non-empty")

    tools = await _discover_tools()
    openai_client = _get_openai()

    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in req.messages:
        messages.append({"role": m.role, "content": m.content})

    max_iter = req.max_iterations or MAX_TOOL_ITERATIONS
    traces: list[ToolCallTrace] = []

    for iteration in range(max_iter):
        completion = await openai_client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
        )
        choice = completion.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            log.info("agent.completed", iterations=iteration + 1, tool_calls=len(traces))
            return ChatResponse(
                answer=msg.content or "",
                tool_calls=traces,
                iterations=iteration + 1,
            )

        # Append assistant turn (with tool calls) to the conversation.
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        # Execute each tool call.
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            log.info("agent.tool_call", name=tc.function.name, args=args)
            try:
                tool_result = await _call_mcp_tool(tc.function.name, args)
            except Exception as exc:  # noqa: BLE001
                tool_result = json.dumps({"error": str(exc)})
                log.warning("agent.tool_error", name=tc.function.name, error=str(exc))
            traces.append(
                ToolCallTrace(
                    name=tc.function.name,
                    arguments=args,
                    result_preview=tool_result[:500],
                )
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                }
            )

    log.warning("agent.max_iterations_hit", iterations=max_iter, tool_calls=len(traces))
    return ChatResponse(
        answer="Reached max tool iterations without a final answer.",
        tool_calls=traces,
        iterations=max_iter,
    )
