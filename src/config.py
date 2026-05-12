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

    # --- Azure Maps (skeleton: unused; Haversine stub) ---
    azure_maps_subscription_key: str | None = None
    azure_maps_base_url: str = "https://atlas.microsoft.com"

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
