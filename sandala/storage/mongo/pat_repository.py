from __future__ import annotations

from typing import Any


class PatRepository:
    def __init__(self, db):
        self._col = db["_pat_tokens"]

    def ensure_indexes(self) -> None:
        self._col.create_index("id", unique=True)
        self._col.create_index("subject_id")
        self._col.create_index("created_by")
        self._col.create_index("expires_at")
        self._col.create_index("revoked_at")

    def create(self, pat_doc: dict[str, Any]) -> dict[str, Any]:
        self._col.insert_one(dict(pat_doc))
        return pat_doc

    def find_by_id(self, pat_id: str) -> dict[str, Any] | None:
        doc = self._col.find_one({"id": pat_id}, {"_id": 0})
        if doc is None:
            return None
        return doc

    def find_many(self, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return list(self._col.find(query or {}, {"_id": 0}).sort("cdate", 1))

    def update_by_id(self, pat_id: str, fields: dict[str, Any]) -> bool:
        result = self._col.update_one(
            {"id": pat_id},
            {"$set": fields},
            upsert=False,
        )
        return result.modified_count > 0
