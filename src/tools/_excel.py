"""Excel parsing helpers shared by ingest tools.

Centralizes header normalization so that minor variations in customer Excel
column naming (case, punctuation, extra whitespace) don't break ingestion.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_header(s: str) -> str:
    """Lowercase + collapse non-alphanumerics to single underscores."""
    return _NON_ALNUM.sub("_", str(s).strip().lower()).strip("_")


def read_sheet(file_path: str, sheet_name: str) -> pd.DataFrame:
    """Read an Excel sheet and normalize column headers."""
    df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
    df.columns = [normalize_header(c) for c in df.columns]
    return df


def pick(row: dict[str, Any], *candidates: str, default: Any = None) -> Any:
    """Return the first non-null value for any normalized header candidate."""
    for c in candidates:
        key = normalize_header(c)
        if key in row:
            v = row[key]
            if v is None:
                continue
            if isinstance(v, float) and pd.isna(v):
                continue
            return v
    return default


def to_int(v: Any, default: int = 0) -> int:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def to_float(v: Any, default: float = 0.0) -> float:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def to_str(v: Any, default: str | None = None) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    s = str(v).strip()
    return s if s else default


def to_bool(v: Any, default: bool = False) -> bool:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in {"true", "yes", "y", "1", "t"}
