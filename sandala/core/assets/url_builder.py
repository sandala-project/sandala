from __future__ import annotations


def build_asset_url(storage_key: str, *, public_base_url: str | None) -> str:
    if isinstance(public_base_url, str) and public_base_url.strip():
        return f"{public_base_url.rstrip('/')}/{storage_key}"
    return f"/{storage_key}"
