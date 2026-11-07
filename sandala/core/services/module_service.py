from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import UUID

from sandala.core.access import actor_has_role_at_least
from sandala.core.errors import AuthorizationError, ConflictError, NotFoundError, ParameterInvalidError, RequestBodyInvalidError, ValidationError

_USERS_MODULE = "users"
_USER_ENTITY = "user"
_GROUP_ENTITY = "group"


class ModuleService:
    def __init__(self, module_repo, entity_repo, node_repo):
        self._module_repo = module_repo
        self._entity_repo = entity_repo
        self._node_repo = node_repo

    def list_modules(self, *, actor: dict[str, Any]) -> list[dict[str, Any]]:
        self._require_admin_or_superuser(actor)
        return self._module_repo.list_modules()

    def get_module(self, name: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        self._require_admin_or_superuser(actor)
        doc = self._module_repo.get_module(name)
        if doc is None:
            raise NotFoundError(f"Module '{name}' not found")
        return doc

    def create_module(self, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        self._require_superuser(actor)
        candidate = self._validate_create_payload(payload, actor=actor)
        if self._module_repo.module_exists(candidate["name"]):
            raise ConflictError(f"Module '{candidate['name']}' already exists")
        self._node_repo.ensure_module_indexes(candidate["name"])
        return self._module_repo.create_module(candidate)

    def patch_module(self, name: str, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        self._require_superuser(actor)
        current = self._module_repo.get_module(name)
        if current is None:
            raise NotFoundError(f"Module '{name}' not found")
        patch = self._validate_patch_payload(name, payload)
        if not patch:
            return current
        updated = self._module_repo.update_module(name, patch)
        if updated is None:
            raise NotFoundError(f"Module '{name}' not found")
        return updated

    def delete_module(self, name: str, *, actor: dict[str, Any]) -> None:
        self._require_superuser(actor)
        current = self._module_repo.get_module(name)
        if current is None:
            raise NotFoundError(f"Module '{name}' not found")
        if self._entity_repo.module_exists(name):
            raise ConflictError("Module cannot be deleted while entities exist")
        if self._node_repo.count_active_in_module(name) > 0:
            raise ConflictError("Module cannot be deleted while non-deleted nodes exist")
        self._module_repo.delete_module(name)

    def _validate_create_payload(self, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RequestBodyInvalidError("Module payload must be an object")
        name = payload.get("name")
        description = payload.get("description")
        root_perm = payload.get("root_perm")
        root_owner = payload.get("root_owner")
        root_group = payload.get("root_group")
        root_children_entities = payload.get("root_children_entities")

        if not isinstance(name, str) or not name.strip():
            raise ParameterInvalidError("Field 'name' must be a non-empty string")
        if not isinstance(description, str):
            raise ParameterInvalidError("Field 'description' must be a string")
        self._validate_root_perm(root_perm)
        normalized_owner = self._resolve_root_owner(root_owner, actor=actor)
        normalized_group = self._resolve_root_group(root_group, actor=actor)
        normalized_root_children = self._validate_root_children_entities_for_create(
            name.strip(),
            root_children_entities,
        )
        self._validate_root_subject_references(normalized_owner, normalized_group)
        return {
            "name": name.strip(),
            "description": description.strip(),
            "root_perm": deepcopy(root_perm),
            "root_owner": normalized_owner,
            "root_group": normalized_group,
            "root_children_entities": normalized_root_children,
        }

    def _validate_patch_payload(self, module: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RequestBodyInvalidError("Module payload must be an object")
        patch: dict[str, Any] = {}
        allowed = {"description", "root_perm", "root_owner", "root_group", "root_children_entities"}
        unknown = set(payload.keys()) - allowed
        if unknown:
            invalid = sorted(unknown)[0]
            raise ParameterInvalidError(f"Field '{invalid}' is not allowed for module patch")
        if "description" in payload:
            description = payload["description"]
            if not isinstance(description, str):
                raise ParameterInvalidError("Field 'description' must be a string")
            patch["description"] = description.strip()
        if "root_perm" in payload:
            self._validate_root_perm(payload["root_perm"])
            patch["root_perm"] = deepcopy(payload["root_perm"])
        if "root_owner" in payload:
            patch["root_owner"] = self._validate_uuid_field(payload["root_owner"], "root_owner")
        if "root_group" in payload:
            patch["root_group"] = self._validate_uuid_field(payload["root_group"], "root_group")
        if "root_children_entities" in payload:
            patch["root_children_entities"] = self._validate_root_children_entities(
                module,
                payload["root_children_entities"],
            )
        if "root_owner" in patch or "root_group" in patch:
            self._validate_root_subject_references(
                patch.get("root_owner"),
                patch.get("root_group"),
            )
        return patch

    def _validate_root_perm(self, root_perm: Any) -> None:
        if not isinstance(root_perm, dict):
            raise ValidationError("Field 'root_perm' must be an object")
        if set(root_perm.keys()) != {"owner", "group", "others"}:
            raise ValidationError("Field 'root_perm' must contain exactly 'owner', 'group' and 'others' sections")
        for role in ("owner", "group", "others"):
            section = root_perm.get(role)
            if not isinstance(section, dict):
                raise ValidationError(f"Field 'root_perm.{role}' must be an object")
            if set(section.keys()) != {"p"}:
                raise ValidationError(f"Field 'root_perm.{role}' must contain only boolean key 'p'")
            if not isinstance(section.get("p"), bool):
                raise ValidationError(f"Field 'root_perm.{role}.p' must be boolean")

    def _require_superuser(self, actor: dict[str, Any]) -> None:
        if not actor_has_role_at_least(actor, "superuser"):
            raise AuthorizationError("Only superuser can access module operations")

    def _require_admin_or_superuser(self, actor: dict[str, Any]) -> None:
        if not actor_has_role_at_least(actor, "admin"):
            raise AuthorizationError("Only admin or superuser can access module operations")

    def _resolve_root_owner(self, value: Any, *, actor: dict[str, Any]) -> str:
        if value is None:
            value = actor.get("user_id") if isinstance(actor, dict) else None
        if value is None:
            raise ValidationError("Field 'root_owner' must be provided or actor must include user_id")
        return self._validate_uuid_field(value, "root_owner")

    def _resolve_root_group(self, value: Any, *, actor: dict[str, Any]) -> str:
        if value is None:
            value = actor.get("primary_group") if isinstance(actor, dict) else None
        if value is None:
            raise ValidationError("Field 'root_group' must be provided or actor must include primary_group")
        return self._validate_uuid_field(value, "root_group")

    def _validate_uuid_field(self, value: Any, field_name: str) -> str:
        if not isinstance(value, str) or not value:
            raise ParameterInvalidError(f"Field '{field_name}' must be a non-empty UUID string")
        try:
            UUID(value)
        except ValueError as exc:
            raise ParameterInvalidError(f"Field '{field_name}' must be a valid UUID string") from exc
        return value

    def _validate_root_children_entities_for_create(self, module: str, value: Any) -> list[str]:
        entities = self._validate_root_children_entities(module, value)
        if entities:
            raise ValidationError("Field 'root_children_entities' must be an empty array when creating a module")
        return entities

    def _validate_root_children_entities(self, module: str, value: Any) -> list[str]:
        if not isinstance(value, list):
            raise ValidationError("Field 'root_children_entities' must be an array of entity names")

        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValidationError("Field 'root_children_entities' must contain non-empty strings")
            entity = item.strip()
            if entity in seen:
                continue
            if not self._entity_repo.entity_exists(module, entity):
                raise ValidationError(
                    f"Field 'root_children_entities' references unknown entity '{entity}' in module '{module}'"
                )
            seen.add(entity)
            normalized.append(entity)
        return normalized

    def _validate_root_subject_references(
        self,
        root_owner: str | None,
        root_group: str | None,
    ) -> None:
        if root_owner is not None:
            owner = self._node_repo.find_one(
                _USERS_MODULE,
                {"id": root_owner, "entity": _USER_ENTITY, "deleted": False},
                {"_id": 0, "id": 1},
            )
            if owner is None:
                raise ValidationError(f"Field 'root_owner' references unknown users/{_USER_ENTITY} '{root_owner}'")
        if root_group is not None:
            group = self._node_repo.find_one(
                _USERS_MODULE,
                {"id": root_group, "entity": _GROUP_ENTITY, "deleted": False},
                {"_id": 0, "id": 1},
            )
            if group is None:
                raise ValidationError(f"Field 'root_group' references unknown users/{_GROUP_ENTITY} '{root_group}'")
