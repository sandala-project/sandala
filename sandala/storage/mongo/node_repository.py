from __future__ import annotations

from pymongo import UpdateOne
from pymongo.errors import DuplicateKeyError, OperationFailure

from sandala.storage.errors import StorageQueryRejectedError


_QUERY_REJECTION_MESSAGES = {
    # BadValue is not specific to parallel-array sorting.
    2: "Query contains values or operations unsupported by the database",
    13103: "Sort contains too many fields",
    51091: "Query contains an invalid regular expression",
}


class NodeRepository:
    def __init__(self, db):
        self._db = db

    def collection(self, module: str):
        return self._db[module]

    def ensure_module_indexes(self, module: str) -> None:
        collection = self.collection(module)
        collection.create_index("id", name="sandala_id_unique", unique=True)
        collection.create_index(
            [("entity", 1), ("deleted", 1), ("_id", 1)],
            name="sandala_entity_deleted_id",
        )
        collection.create_index(
            [("parent", 1), ("deleted", 1), ("_id", 1)],
            name="sandala_parent_deleted_id",
        )

    def count_active_in_module(self, module: str) -> int:
        return self.collection(module).count_documents({"deleted": False})

    def count_active_in_entity(self, module: str, entity: str) -> int:
        return self.collection(module).count_documents({"entity": entity, "deleted": False})

    def iter_by_entity(self, module: str, entity: str):
        return self.collection(module).find({"entity": entity}, {"_id": 0})

    def find_by_id(self, module: str, node_id: str, *, deleted: bool | None = None):
        query: dict[str, object] = {"id": node_id}
        if deleted is not None:
            query["deleted"] = deleted
        return self.collection(module).find_one(query, {"_id": 0})

    def find_active_by_ids(self, module: str, node_ids: set[str]) -> list[dict]:
        if not node_ids:
            return []
        return list(
            self.collection(module).find(
                {"id": {"$in": sorted(node_ids)}, "deleted": False},
                {"_id": 0, "id": 1, "entity": 1, "owner": 1, "group": 1, "perm": 1},
            )
        )

    def find_one(
        self,
        module: str,
        query: dict,
        projection: dict | None = None,
    ):
        effective_projection = {"_id": 0} if projection is None else projection
        return self.collection(module).find_one(query, effective_projection)

    def insert_node(self, module: str, node: dict) -> dict | None:
        try:
            self.collection(module).insert_one(node)
        except DuplicateKeyError:
            return None
        return self.collection(module).find_one({"id": node["id"]}, {"_id": 0})

    def replace_node(self, module: str, node: dict) -> dict | None:
        try:
            self.collection(module).replace_one({"id": node["id"]}, node, upsert=False)
        except DuplicateKeyError:
            return None
        return self.collection(module).find_one({"id": node["id"]}, {"_id": 0})

    def bulk_update_fields(self, module: str, updates: list[dict]) -> int:
        operations = [
            UpdateOne(
                {"id": update["id"], "deleted": False},
                {"$set": update["fields"]},
            )
            for update in updates
        ]
        if not operations:
            return 0
        result = self.collection(module).bulk_write(operations, ordered=True)
        return result.modified_count

    def find_descendants(self, module: str, node_id: str):
        return list(self.collection(module).find({"ancestors": node_id}, {"_id": 0}))

    def find_active_subtree(self, module: str, node_id: str):
        """Return the active subtree in deterministic parent-before-child order."""
        return list(
            self.collection(module)
            .find(
                {
                    "deleted": False,
                    "$or": [
                        {"id": node_id},
                        {"ancestors": node_id},
                    ],
                },
                {"_id": 0},
            )
            .sort([("depth", 1), ("id", 1)])
        )

    def update_descendants_hierarchy(
        self,
        module: str,
        node_id: str,
        new_prefix: list[str],
        old_prefix_len: int,
        depth_delta: int,
    ) -> None:
        pipeline = [
            {
                "$set": {
                    "ancestors": {
                        "$concatArrays": [
                            new_prefix,
                            {
                                "$slice": [
                                    "$ancestors",
                                    old_prefix_len,
                                    {"$size": "$ancestors"},
                                ]
                            },
                        ]
                    },
                    "depth": {"$add": ["$depth", depth_delta]},
                }
            }
        ]
        self.collection(module).update_many({"ancestors": node_id}, pipeline)

    def soft_delete_nodes(self, module: str, node_ids: list[str], mdate: str) -> int:
        if not node_ids:
            return 0
        result = self.collection(module).update_many(
            {
                "id": {"$in": node_ids},
                "deleted": False,
            },
            {
                "$set": {
                    "deleted": True,
                    "mdate": mdate,
                }
            },
        )
        return result.modified_count

    def aggregate(self, module: str, pipeline: list[dict]):
        try:
            return list(self.collection(module).aggregate(pipeline))
        except OperationFailure as exc:
            message = _QUERY_REJECTION_MESSAGES.get(exc.code)
            if message is None:
                raise
            raise StorageQueryRejectedError(message) from exc
