from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

from jsonschema import Draft7Validator, FormatChecker
from pymongo import UpdateOne

from sandala.bootstrap import build_container
from sandala.core.validation.schema_validator import build_effective_node_schema

from .generate import generate_dataset
from .schemas import ENTITIES, MODULE, schemas, placeholder_schema
from .source import load_snapshot, normalize_records


def seed(*, mongo_uri: str | None = None, mongo_db: str | None = None, reset: bool = False, book_count: int = 1200, source_snapshot: str | None = None) -> dict[str, int]:
    config = {}
    if mongo_uri:
        config["MONGO_URI"] = mongo_uri
    if mongo_db:
        config["MONGO_DB"] = mongo_db
    container = build_container(config)
    actor = _root_actor(container)
    module_service = container["module_service"]
    entity_service = container["entity_service"]
    node_repo = container["node_repo"]

    if reset and container["module_repo"].get_module(MODULE):
        node_repo.collection(MODULE).drop()
        for entity in reversed(ENTITIES):
            entity_service.delete(MODULE, entity, actor=actor)
        module_service.delete_module(MODULE, actor=actor)

    _ensure_module(module_service, container, actor)
    _ensure_schemas(entity_service, actor)
    records = normalize_records(load_snapshot(source_snapshot), book_count) if source_snapshot else None
    data = generate_dataset(book_count=book_count, records=records)
    for document in data["_all"]:
        document["owner"] = actor["user_id"]
        document["group"] = actor["primary_group"]
    _validate_nodes(data["_all"], schemas())
    operations = [UpdateOne({"id": document["id"]}, {"$set": document}, upsert=True) for document in data["_all"]]
    node_repo.collection(MODULE).bulk_write(operations, ordered=False)
    module_service.patch_module(MODULE, {"root_children_entities": ["CatalogFolder"]}, actor=actor)
    return {entity: len(data[entity]) for entity in ENTITIES}


def _root_actor(container) -> dict:
    config = container["config"]
    user = container["node_repo"].find_one("users", {"entity": "user", "deleted": False, "username": config["ROOT_USERNAME"]}, {"id": 1, "primary_group": 1})
    if not user:
        raise RuntimeError("Root user was not found; start Sandala once with SANDALA_ROOT_PASSWORD")
    return {"user_id": user["id"], "primary_group": user["primary_group"], "groups": [user["primary_group"]], "role": "superuser", "auth_type": "seed"}


def _ensure_module(module_service, container, actor) -> None:
    if container["module_repo"].get_module(MODULE):
        return
    module_service.create_module({"name": MODULE, "description": "Demo library", "root_owner": actor["user_id"], "root_group": actor["primary_group"], "root_perm": {"owner": {"p": True}, "group": {"p": True}, "others": {"p": True}}, "root_children_entities": []}, actor=actor)


def _ensure_schemas(entity_service, actor) -> None:
    current = set()
    for item in entity_service.list_entities(MODULE, actor=actor):
        current.add(item["title"])
    for entity in ENTITIES:
        if entity not in current:
            entity_service.create(MODULE, entity, placeholder_schema(entity), actor=actor)
    for entity, schema in schemas().items():
        entity_service.update(MODULE, entity, schema, actor=actor)


def _validate_nodes(nodes: list[dict], schema_map: dict) -> None:
    validators = {entity: Draft7Validator(build_effective_node_schema(schema), format_checker=FormatChecker()) for entity, schema in schema_map.items()}
    for document in nodes:
        errors = sorted(validators[document["entity"]].iter_errors(document), key=lambda error: list(error.path))
        if errors:
            path = ".".join(str(part) for part in errors[0].path)
            raise ValueError(f"Generated {document['entity']} {document['id']} is invalid at {path}: {errors[0].message}")


def main() -> None:
    parser = ArgumentParser(description="Seed the isolated Sandala Open Library demo dataset")
    parser.add_argument("--mongo-uri")
    parser.add_argument("--mongo-db")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--books", type=int, default=1200)
    parser.add_argument("--source-snapshot", type=Path, help="A JSON snapshot produced by demo_data.library.fetch")
    args = parser.parse_args()
    counts = seed(mongo_uri=args.mongo_uri, mongo_db=args.mongo_db, reset=args.reset, book_count=args.books, source_snapshot=str(args.source_snapshot) if args.source_snapshot else None)
    for entity, count in counts.items():
        print(f"[demo-seed] {entity}: {count}")


if __name__ == "__main__":
    main()
