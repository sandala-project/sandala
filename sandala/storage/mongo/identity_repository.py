from __future__ import annotations

from typing import Any


class IdentityRepository:
    def __init__(self, db, *, user_module: str, user_entity: str):
        self._col = db[user_module]
        self._user_entity = user_entity

    def ensure_indexes(self) -> None:
        self._col.create_index(
            "username",
            name="sandala_user_username_unique",
            unique=True,
            partialFilterExpression={"entity": self._user_entity},
        )
        self._col.create_index(
            "email",
            name="sandala_user_email_unique",
            unique=True,
            partialFilterExpression={
                "entity": self._user_entity,
                "email": {"$type": "string"},
            },
        )

    def find_active_by_username_or_email(self, login: str) -> dict[str, Any] | None:
        normalized = login.strip().lower()
        doc = self._col.find_one(
            {
                "entity": self._user_entity,
                "deleted": False,
                "active": True,
                "$or": [
                    {"username": normalized},
                    {"email": normalized},
                ],
            },
            {"_id": 0},
        )
        if doc is None:
            return None
        return doc

    def find_by_id(self, user_id: str) -> dict[str, Any] | None:
        doc = self._col.find_one(
            {
                "entity": self._user_entity,
                "id": user_id,
                "deleted": False,
            },
            {"_id": 0},
        )
        if doc is None:
            return None
        return doc
