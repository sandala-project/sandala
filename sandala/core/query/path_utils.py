from __future__ import annotations

from sandala.core.errors import QueryValidationError


def split_field_path(path: str, *, allow_wildcard: bool = False) -> list[str]:
    if not isinstance(path, str) or not path:
        raise QueryValidationError("Field path must be a non-empty string")
    parts = path.split(".")
    for index, part in enumerate(parts):
        if allow_wildcard and part == "*" and index == len(parts) - 1:
            continue
        if not part or part.startswith("$") or "*" in part or "\x00" in part:
            raise QueryValidationError(f"Invalid field path '{path}'")
    return parts


def relative_under_prefix(path: str, prefix: str) -> str | None:
    if path == prefix:
        return ""
    dotted = f"{prefix}."
    if path.startswith(dotted):
        return path[len(dotted) :]
    return None
