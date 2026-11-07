from __future__ import annotations

from typing import Any


class AuthSessionRepository:
    def __init__(self, db):
        self._col = db["_auth_sessions"]

    def ensure_indexes(self) -> None:
        self._col.create_index("session_hash", unique=True)
        self._col.create_index("user_id")
        self._col.create_index("expires_at")
        self._col.create_index("max_expires_at")
        self._col.create_index("revoked_at")

    def create(self, session_doc: dict[str, Any]) -> dict[str, Any]:
        self._col.insert_one(dict(session_doc))
        return session_doc

    def find_active_by_hash(self, session_hash: str) -> dict[str, Any] | None:
        doc = self._col.find_one(
            {
                "session_hash": session_hash,
                "revoked_at": None,
            },
            {"_id": 0},
        )
        if doc is None:
            return None
        return doc

    def renew_by_hash(self, session_hash: str, *, expires_at: str, mdate: str) -> bool:
        result = self._col.update_one(
            {
                "session_hash": session_hash,
                "revoked_at": None,
            },
            {
                "$set": {
                    "expires_at": expires_at,
                    "mdate": mdate,
                }
            },
            upsert=False,
        )
        return result.modified_count > 0

    def revoke_by_hash(self, session_hash: str, revoked_at: str) -> bool:
        result = self._col.update_one(
            {
                "session_hash": session_hash,
                "revoked_at": None,
            },
            {
                "$set": {
                    "revoked_at": revoked_at,
                    "mdate": revoked_at,
                }
            },
            upsert=False,
        )
        return result.modified_count > 0
