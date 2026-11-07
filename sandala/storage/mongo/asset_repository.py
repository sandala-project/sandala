from __future__ import annotations

from typing import Any


class AssetRepository:
    def __init__(self, db):
        self._col = db["_assets"]

    def ensure_indexes(self) -> None:
        self._col.create_index("id", unique=True)
        self._col.create_index("storage_key", unique=True)
        self._col.create_index([("module", 1), ("entity", 1), ("field", 1)])

    def create(self, doc: dict[str, Any]) -> dict[str, Any]:
        self._col.insert_one(dict(doc))
        return doc

    def find_by_id(self, asset_id: str) -> dict[str, Any] | None:
        return self._col.find_one({"id": asset_id}, {"_id": 0})

    def find_by_storage_key(self, storage_key: str) -> dict[str, Any] | None:
        return self._col.find_one({"storage_key": storage_key}, {"_id": 0})
