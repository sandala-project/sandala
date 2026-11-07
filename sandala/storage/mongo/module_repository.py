from __future__ import annotations

from typing import Any


class ModuleRepository:
    def __init__(self, db):
        self._col = db["_modules"]
        self._col.create_index("name", unique=True)

    def list_modules(self) -> list[dict[str, Any]]:
        cursor = self._col.find({}, {"_id": 0}).sort("name", 1)
        return list(cursor)

    def get_module(self, name: str) -> dict[str, Any] | None:
        return self._col.find_one({"name": name}, {"_id": 0})

    def module_exists(self, name: str) -> bool:
        return self._col.find_one({"name": name}, {"_id": 1}) is not None

    def create_module(self, doc: dict[str, Any]) -> dict[str, Any]:
        self._col.insert_one(doc)
        return self.get_module(doc["name"])

    def update_module(self, name: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        self._col.update_one({"name": name}, {"$set": patch}, upsert=False)
        return self.get_module(name)

    def delete_module(self, name: str) -> None:
        self._col.delete_one({"name": name})
