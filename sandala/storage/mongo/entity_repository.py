from __future__ import annotations

from typing import Any


class EntityRepository:
    def __init__(self, db):
        self._col = db["_entities"]

    def list_entities(self, module: str) -> list[dict[str, str]]:
        cursor = self._col.find({"module": module}, {"schema.title": 1, "schema.description": 1})
        return [
            {
                "title": item["schema"].get("title", ""),
                "description": item["schema"].get("description", ""),
            }
            for item in cursor
        ]

    def get_schema(self, module: str, entity: str) -> dict[str, Any] | None:
        doc = self._col.find_one({"module": module, "entity": entity})
        if not doc:
            return None
        return doc["schema"]

    def entity_exists(self, module: str, entity: str) -> bool:
        return self._col.find_one({"module": module, "entity": entity}, {"_id": 1}) is not None

    def module_exists(self, module: str) -> bool:
        return self._col.find_one({"module": module}, {"_id": 1}) is not None

    def create(self, module: str, entity: str, schema: dict[str, Any]) -> None:
        self._col.insert_one({"module": module, "entity": entity, "schema": schema})

    def update(self, module: str, entity: str, schema: dict[str, Any]) -> None:
        self._col.update_one(
            {"module": module, "entity": entity},
            {"$set": {"schema": schema}},
            upsert=False,
        )

    def delete(self, module: str, entity: str) -> None:
        self._col.delete_one({"module": module, "entity": entity})

    def iter_all(self) -> list[dict[str, Any]]:
        return list(self._col.find({}))

    def replace_schema(self, doc_id: Any, schema: dict[str, Any]) -> None:
        self._col.update_one({"_id": doc_id}, {"$set": {"schema": schema}})

    def get_module_schemas(self, module: str) -> dict[str, dict[str, Any]]:
        docs = self._col.find({"module": module}, {"entity": 1, "schema": 1})
        return {
            doc["entity"]: doc["schema"]
            for doc in docs
        }
