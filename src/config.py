"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings for the Routing Optimization MCP server.

    Values are loaded (in order of precedence) from real environment variables,
    then a local ``.env`` file. See ``.env.example`` for the full list.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Cosmos DB ---
    azure_cosmos_endpoint: str = Field(..., description="Cosmos DB account endpoint URL")
    azure_cosmos_database: str = Field(default="routing_optimization")

    # --- Azure Maps (live when ``azure_maps_client_id`` is set; otherwise Haversine) ---
    azure_maps_subscription_key: str | None = None
    azure_maps_client_id: str | None = None
    azure_maps_base_url: str = "https://atlas.microsoft.com"
    # Route Matrix v2 (api-version=2025-01-01) supports up to 2500 cells in sync mode.
    # We keep a tighter default safety guard; raise via env if needed.
    azure_maps_matrix_max_cells: int = 700
    # Soft per-replica daily cell budget. None disables. Logs WARNING at 80%, ERROR
    # and refuses the call at 100%.
    azure_maps_matrix_daily_budget_cells: int | None = None

    # --- Observability ---
    application_insights_connection_string: str | None = None

    # --- MCP transport ---
    mcp_transport: Literal["http", "stdio"] = "http"
    mcp_http_host: str = "0.0.0.0"
    mcp_http_port: int = 8000
    mcp_log_level: str = "INFO"

    # --- Routing defaults ---
    default_routing_profile: str = "truck"
    matrix_cache_ttl_sec: int = 86_400

    # --- Albertsons constants ---
    default_dc_code: str = "52-DC"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()  # type: ignore[call-arg]
