from __future__ import annotations

import re


_FILENAME_CLEAN_RE = re.compile(r"[^A-Za-z0-9._-]+")
_FIELD_SEGMENT_RE = re.compile(r"[^A-Za-z0-9_-]+")


def build_storage_key(*, module: str, entity: str, field: str, asset_id: str, source_filename: str | None, extension: str) -> str:
    normalized_field = _normalize_field_segment(field)
    basename = _basename_for_key(source_filename, extension)
    return f"assets/{module}/{entity}/{normalized_field}/{asset_id}/{basename}"


def _basename_for_key(source_filename: str | None, extension: str) -> str:
    if isinstance(source_filename, str) and source_filename.strip():
        stem = source_filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
        cleaned = _FILENAME_CLEAN_RE.sub("-", stem).strip(".-")
        if cleaned:
            return f"{cleaned}.{extension}"
    return f"asset.{extension}"


def _normalize_field_segment(field: str) -> str:
    normalized = "__".join(segment.strip() for segment in field.split(".") if segment.strip())
    normalized = _FIELD_SEGMENT_RE.sub("-", normalized).strip("-")
    return normalized or "field"
