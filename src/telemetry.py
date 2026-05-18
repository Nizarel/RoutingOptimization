"""OpenTelemetry → Azure Monitor (Application Insights) initialization.

A no-op when ``APPLICATIONINSIGHTS_CONNECTION_STRING`` is not configured, so
unit tests and local stdio runs stay silent.

When the env var is set, this module:

* Configures the Azure Monitor distro (logs + traces + metrics).
* Auto-instruments ``httpx`` so calls to Azure Maps are traced.
* Bridges Python ``logging`` (and structlog through it) so JSON log lines
  arrive in Application Insights as traces carrying the active trace_id.

The function is idempotent — calling it twice is safe.
"""
from __future__ import annotations

import os

from src.logging_config import get_logger

log = get_logger(__name__)

_INITIALIZED = False


def configure_telemetry() -> bool:
    """Initialize Azure Monitor + auto-instrumentation. Returns True if enabled."""
    global _INITIALIZED
    if _INITIALIZED:
        return True

    conn = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn:
        log.info("telemetry.disabled", reason="connection_string_not_set")
        return False

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        configure_azure_monitor(
            connection_string=conn,
            resource_attributes={
                "service.name": "routing-optimization-mcp",
                "service.namespace": "routing",
            },
            disable_offline_storage=False,
        )
        HTTPXClientInstrumentor().instrument()
    except Exception as exc:  # noqa: BLE001
        log.warning("telemetry.init_failed", error=str(exc))
        return False

    _INITIALIZED = True
    log.info("telemetry.enabled", exporter="azure_monitor")
    return True
