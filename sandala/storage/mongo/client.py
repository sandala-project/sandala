from __future__ import annotations

from pymongo import MongoClient


def create_mongo_database(config: dict | None = None):
    cfg = config or {}
    uri = cfg.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = cfg.get("MONGO_DB", "sandala")
    client = MongoClient(uri)
    return client[db_name]
