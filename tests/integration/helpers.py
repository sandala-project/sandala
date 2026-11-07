from __future__ import annotations

import re
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from sandala.bootstrap import build_container
from sandala.core.errors import ConflictError, NotFoundError

SUPERUSER_ACTOR = {"role": "superuser"}
S3_TEST_IMAGE = (
    "chrislusf/seaweedfs:4.52"
    "@sha256:57877e32bb90073b37dc109b438ba66e84fd5ed9ced5f5c04f56444ef243ce59"
)


class SuperuserEntityServiceProxy:
    def __init__(self, service, module_service):
        self._service = service
        self._module_service = module_service

    def __getattr__(self, name):
        return getattr(self._service, name)

    def list_entities(self, module: str):
        return self._service.list_entities(module, actor=SUPERUSER_ACTOR)

    def get_schema(self, module: str, entity: str):
        return self._service.get_schema(module, entity, actor=SUPERUSER_ACTOR)

    def create(self, module: str, entity: str, schema: dict):
        self._ensure_module(module)
        return self._service.create(module, entity, schema, actor=SUPERUSER_ACTOR)

    def update(self, module: str, entity: str, schema: dict):
        return self._service.update(module, entity, schema, actor=SUPERUSER_ACTOR)

    def delete(self, module: str, entity: str):
        return self._service.delete(module, entity, actor=SUPERUSER_ACTOR)

    def _ensure_module(self, module: str) -> None:
        try:
            self._module_service.get_module(module, actor=SUPERUSER_ACTOR)
            return
        except NotFoundError:
            pass
        root_user = self._module_service._node_repo.find_one(
            "users",
            {"entity": "user", "deleted": False, "username": "admin"},
            {"_id": 0, "id": 1, "primary_group": 1},
        )
        if root_user is None:
            raise RuntimeError("Bootstrap users/admin node is missing")
        root_owner = root_user.get("id")
        root_group = root_user.get("primary_group")
        if not isinstance(root_owner, str) or not isinstance(root_group, str):
            raise RuntimeError("Bootstrap users/admin node has invalid ids")
        try:
            self._module_service.create_module(
                {
                    "name": module,
                    "description": module,
                    "root_owner": root_owner,
                    "root_group": root_group,
                    "root_children_entities": [],
                    "root_perm": {
                        "owner": {"p": True},
                        "group": {"p": True},
                        "others": {"p": True},
                    },
                },
                actor=SUPERUSER_ACTOR,
            )
        except ConflictError:
            return


def build_integration_config(mongo_uri: str, mongo_db: str = "sandala_it", overrides: dict | None = None) -> dict:
    config = {
        "MONGO_URI": mongo_uri,
        "MONGO_DB": mongo_db,
        "ROOT_USERNAME": "admin",
        "ROOT_PASSWORD": "Admin123!",
        "DEFAULT_GROUP_GROUPNAME": "default",
    }
    if overrides:
        config.update(overrides)
    return config


def build_services(config: dict):
    container = build_container(config)
    entity_service = SuperuserEntityServiceProxy(container["entity_service"], container["module_service"])
    node_service = container["node_service"]
    node_repo = node_service._node_repo
    asset_service = container.get("asset_service")
    return entity_service, node_service, node_repo, asset_service, config


@contextmanager
def mongo_services(mongo_image: str = "mongo:7.0", mongo_db: str = "sandala_it"):
    mongodb_mod = pytest.importorskip("testcontainers.mongodb")
    wait_mod = pytest.importorskip("testcontainers.core.wait_strategies")
    MongoDbContainer = mongodb_mod.MongoDbContainer
    LogMessageWaitStrategy = wait_mod.LogMessageWaitStrategy

    class StableMongoDbContainer(MongoDbContainer):
        def _connect(self) -> None:
            LogMessageWaitStrategy(re.compile(r"waiting for connections", re.IGNORECASE)).wait_until_ready(self)

    with StableMongoDbContainer(mongo_image) as mongo:
        config = build_integration_config(
            mongo.get_connection_url(),
            mongo_db=mongo_db,
        )
        entity_service, node_service, node_repo, _asset_service, _config = build_services(
            config,
        )
        yield entity_service, node_service, node_repo


@contextmanager
def mongo_s3_services(
    mongo_image: str = "mongo:7.0",
    mongo_db: str = "sandala_it",
    s3_image: str = S3_TEST_IMAGE,
    bucket_name: str = "sandala-test",
    extra_config: dict | None = None,
):
    boto3 = pytest.importorskip("boto3")
    botocore_config = pytest.importorskip("botocore.config")
    BotoConfig = botocore_config.Config
    mongodb_mod = pytest.importorskip("testcontainers.mongodb")
    wait_mod = pytest.importorskip("testcontainers.core.wait_strategies")
    container_mod = pytest.importorskip("testcontainers.core.container")
    MongoDbContainer = mongodb_mod.MongoDbContainer
    LogMessageWaitStrategy = wait_mod.LogMessageWaitStrategy
    DockerContainer = container_mod.DockerContainer

    class StableMongoDbContainer(MongoDbContainer):
        def _connect(self) -> None:
            LogMessageWaitStrategy(re.compile(r"waiting for connections", re.IGNORECASE)).wait_until_ready(self)

    with StableMongoDbContainer(mongo_image) as mongo:
        s3 = (
            DockerContainer(s3_image)
            .with_env("AWS_ACCESS_KEY_ID", "sandala-test")
            .with_env("AWS_SECRET_ACCESS_KEY", "sandala-test-secret")
            .with_exposed_ports(8333)
            .with_command("mini -dir=/data")
        )
        with s3:
            endpoint = f"http://{s3.get_container_host_ip()}:{s3.get_exposed_port(8333)}"
            client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id="sandala-test",
                aws_secret_access_key="sandala-test-secret",
                region_name="us-east-1",
                config=BotoConfig(
                    s3={"addressing_style": "path"},
                    connect_timeout=1,
                    read_timeout=5,
                    retries={"max_attempts": 0},
                ),
            )
            _wait_s3_ready(client)
            client.create_bucket(Bucket=bucket_name)
            merged_extra = {
                "ASSET_STORAGE_BACKEND": "s3",
                "ASSET_S3_ENDPOINT": endpoint,
                "ASSET_S3_BUCKET": bucket_name,
                "ASSET_S3_REGION": "us-east-1",
                "ASSET_S3_ACCESS_KEY": "sandala-test",
                "ASSET_S3_SECRET_KEY": "sandala-test-secret",
                "ASSET_S3_ADDRESSING_STYLE": "path",
            }
            if extra_config is not None:
                merged_extra.update(extra_config)
            config = build_integration_config(
                mongo.get_connection_url(),
                mongo_db=mongo_db,
                overrides=merged_extra,
            )
            yield (*build_services(config), client)


@contextmanager
def mongo_local_asset_services(
    asset_root: Path,
    mongo_image: str = "mongo:7.0",
    mongo_db: str = "sandala_it",
    extra_config: dict | None = None,
):
    asset_root.mkdir(parents=True, exist_ok=True)
    merged_extra = {
        "ASSET_STORAGE_BACKEND": "local_fs",
        "ASSET_LOCAL_ROOT": str(asset_root),
    }
    if extra_config:
        merged_extra.update(extra_config)

    mongodb_mod = pytest.importorskip("testcontainers.mongodb")
    wait_mod = pytest.importorskip("testcontainers.core.wait_strategies")
    MongoDbContainer = mongodb_mod.MongoDbContainer
    LogMessageWaitStrategy = wait_mod.LogMessageWaitStrategy

    class StableMongoDbContainer(MongoDbContainer):
        def _connect(self) -> None:
            LogMessageWaitStrategy(re.compile(r"waiting for connections", re.IGNORECASE)).wait_until_ready(self)

    with StableMongoDbContainer(mongo_image) as mongo:
        config = build_integration_config(
            mongo.get_connection_url(),
            mongo_db=mongo_db,
            overrides=merged_extra,
        )
        yield build_services(config)


def _wait_s3_ready(client, *, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_exc = None
    while time.monotonic() < deadline:
        try:
            client.list_buckets()
            return
        except Exception as exc:  # pragma: no cover - exercised only in flaky startup windows
            last_exc = exc
            time.sleep(0.5)
    raise RuntimeError(f"S3 service did not become ready: {last_exc}") from last_exc
