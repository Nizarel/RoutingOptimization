"""Pytest fixtures."""
from __future__ import annotations

import os

# Avoid pulling real Cosmos auth during unit-test imports.
os.environ.setdefault("AZURE_COSMOS_ENDPOINT", "https://example.documents.azure.com:443/")
os.environ.setdefault("AZURE_COSMOS_DATABASE", "routing_optimization")
