from __future__ import annotations

import pytest
from pymongo.errors import ConnectionFailure, DuplicateKeyError, OperationFailure

from sandala.storage.errors import StorageQueryRejectedError
from sandala.storage.mongo.node_repository import NodeRepository


class FakeCollection:
    def __init__(self):
        self.index_calls: list[tuple[object, dict]] = []
        self.documents: list[dict] = []
        self.duplicate_on_insert = False
        self.duplicate_on_replace = False

    def create_index(self, keys, **kwargs):
        self.index_calls.append((keys, kwargs))

    def insert_one(self, node):
        if self.duplicate_on_insert:
            raise DuplicateKeyError("duplicate key")
        self.documents.append(dict(node))

    def replace_one(self, query, node, upsert=False):
        if self.duplicate_on_replace:
            raise DuplicateKeyError("duplicate key")
        for index, document in enumerate(self.documents):
            if document.get("id") == query.get("id"):
                self.documents[index] = dict(node)
                return

    def find_one(self, query, projection):
        for document in self.documents:
            if document.get("id") == query.get("id"):
                return {key: value for key, value in document.items() if key != "_id"}
        return None


class FakeDatabase:
    def __init__(self):
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


def test_ensure_module_indexes_creates_base_indexes():
    database = FakeDatabase()
    repository = NodeRepository(database)

    repository.ensure_module_indexes("library")

    assert database["library"].index_calls == [
        ("id", {"name": "sandala_id_unique", "unique": True}),
        ([("entity", 1), ("deleted", 1), ("_id", 1)], {"name": "sandala_entity_deleted_id"}),
        ([("parent", 1), ("deleted", 1), ("_id", 1)], {"name": "sandala_parent_deleted_id"}),
    ]


def test_insert_node_returns_none_for_duplicate_id():
    database = FakeDatabase()
    repository = NodeRepository(database)
    database["library"].duplicate_on_insert = True

    assert repository.insert_node("library", {"id": "node-1"}) is None


def test_replace_node_returns_none_for_duplicate_key():
    database = FakeDatabase()
    repository = NodeRepository(database)
    database["library"].documents.append({"id": "node-1"})
    database["library"].duplicate_on_replace = True

    assert repository.replace_node("library", {"id": "node-1"}) is None


@pytest.mark.parametrize("during_iteration", [False, True])
@pytest.mark.parametrize("code,message", [
    (2, "Query contains values or operations unsupported by the database"),
    (13103, "Sort contains too many fields"),
    (51091, "Query contains an invalid regular expression"),
])
def test_aggregate_translates_known_rejections_without_exposing_mongo_details(monkeypatch, code, message, during_iteration):
    database = FakeDatabase()
    repository = NodeRepository(database)
    error = OperationFailure("PRIVATE pipeline and database details", code=code)

    def failing_cursor():
        yield {"id": "partial-result"}
        raise error

    def aggregate(pipeline):
        if during_iteration:
            return failing_cursor()
        raise error

    monkeypatch.setattr(database["library"], "aggregate", aggregate, raising=False)
    with pytest.raises(StorageQueryRejectedError) as caught:
        repository.aggregate("library", [])
    assert str(caught.value) == message
    assert caught.value.__cause__ is error


@pytest.mark.parametrize("error", [
    OperationFailure("unknown failure", code=999999),
    OperationFailure("missing code"),
    OperationFailure("database access denied", code=13),
    OperationFailure("query timed out", code=50),
    ConnectionFailure("connection lost"),
    ValueError("unclassified driver failure"),
])
def test_aggregate_preserves_unclassified_failures(monkeypatch, error):
    database = FakeDatabase()
    repository = NodeRepository(database)

    def aggregate(pipeline):
        raise error

    monkeypatch.setattr(database["library"], "aggregate", aggregate, raising=False)
    with pytest.raises(type(error)) as caught:
        repository.aggregate("library", [])
    assert caught.value is error


def test_aggregate_returns_all_cursor_results(monkeypatch):
    database = FakeDatabase()
    repository = NodeRepository(database)
    rows = [{"id": "first"}, {"id": "second"}]
    pipeline = [{"$match": {"deleted": False}}]

    def aggregate(actual_pipeline):
        assert actual_pipeline is pipeline
        return iter(rows)

    monkeypatch.setattr(database["library"], "aggregate", aggregate, raising=False)
    assert repository.aggregate("library", pipeline) == rows
