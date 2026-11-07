from __future__ import annotations

from sandala.config import build_config
from sandala.core.security import SecurityService
from sandala.core.services.asset_service import AssetService
from sandala.core.services.auth_service import AuthService
from sandala.core.services.entity_service import EntityService
from sandala.core.services.module_service import ModuleService
from sandala.core.services.node_hooks import NodeHookRegistry
from sandala.core.services.node_service import NodeService
from sandala.core.users import ensure_users_module, register_users_module_node_hooks
from sandala.core.users.schemas import USER_ENTITY, USER_MODULE
from sandala.storage.mongo.auth_session_repository import AuthSessionRepository
from sandala.storage.mongo.asset_repository import AssetRepository
from sandala.storage.mongo.client import create_mongo_database
from sandala.storage.mongo.entity_repository import EntityRepository
from sandala.storage.mongo.identity_repository import IdentityRepository
from sandala.storage.mongo.module_repository import ModuleRepository
from sandala.storage.mongo.node_repository import NodeRepository
from sandala.storage.mongo.pat_repository import PatRepository
from sandala.storage.blob.local_fs import LocalFsBlobStorage


def build_container(config: dict | None = None):
    cfg = build_config(config)
    db = create_mongo_database(cfg)
    module_repo = ModuleRepository(db)
    entity_repo = EntityRepository(db)
    node_repo = NodeRepository(db)
    identity_repo = IdentityRepository(
        db,
        user_module=USER_MODULE,
        user_entity=USER_ENTITY,
    )
    identity_repo.ensure_indexes()
    auth_session_repo = AuthSessionRepository(db)
    auth_session_repo.ensure_indexes()
    pat_repo = PatRepository(db)
    pat_repo.ensure_indexes()
    asset_repo = AssetRepository(db)
    asset_repo.ensure_indexes()

    security = SecurityService()
    blob_storage = _build_blob_storage(cfg)

    hook_registry = NodeHookRegistry()
    module_service = ModuleService(module_repo, entity_repo, node_repo)
    entity_service = EntityService(entity_repo, node_repo, module_repo)
    node_service = NodeService(entity_repo, node_repo, module_repo, hook_registry=hook_registry)
    asset_service = AssetService(entity_repo, asset_repo, blob_storage, cfg)
    register_users_module_node_hooks(
        hook_registry,
        node_repo,
        module_repo,
        security,
        cfg,
    )
    ensure_users_module(module_repo, entity_repo, node_repo, cfg)

    auth_service = AuthService(identity_repo, auth_session_repo, pat_repo, security, cfg)

    return {
        "config": cfg,
        "module_repo": module_repo,
        "entity_repo": entity_repo,
        "node_repo": node_repo,
        "asset_repo": asset_repo,
        "module_service": module_service,
        "entity_service": entity_service,
        "node_service": node_service,
        "asset_service": asset_service,
        "auth_service": auth_service,
    }


def _build_blob_storage(config: dict):
    backend = config.get("ASSET_STORAGE_BACKEND", "local_fs")
    if backend == "local_fs":
        return LocalFsBlobStorage(config.get("ASSET_LOCAL_ROOT", ".sandala_assets"))
    if backend == "s3":
        from sandala.storage.blob.s3 import S3BlobStorage

        return S3BlobStorage(config)
    raise ValueError(f"Unsupported asset storage backend '{backend}'")
