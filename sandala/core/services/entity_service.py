from __future__ import annotations

from copy import deepcopy
from typing import Any

from jsonschema import Draft7Validator, FormatChecker

from sandala.core.access import actor_has_role_at_least
from sandala.core.errors import AuthorizationError, ConflictError, DocumentValidationError, NotFoundError, ValidationError
from sandala.core.query.schema_utils import unwrap_nullable
from sandala.core.users.schemas import (
    GROUP_ENTITY,
    GROUP_PROTECTED_FIELDS,
    USER_ENTITY,
    USER_MODULE,
    USER_PROTECTED_FIELDS,
)
from sandala.core.validation.schema_validator import (
    EntitySchemaValidator,
    build_effective_node_schema,
    enrich_schema_with_system_fields,
)
from sandala.core.validation.error_normalizer import make_document_validation_error


class EntityService:
    def __init__(self, entity_repo, node_repo, module_repo):
        self._entity_repo = entity_repo
        self._node_repo = node_repo
        self._module_repo = module_repo
        self._validator = EntitySchemaValidator(
            entity_exists=self._entity_exists_any,
            module_exists=self._module_exists,
        )

    def list_entities(
        self,
        module: str,
        *,
        actor: dict[str, Any],
    ) -> list[dict[str, str]]:
        self._require_admin_or_superuser(actor)
        return self._entity_repo.list_entities(module)

    def get_schema(
        self,
        module: str,
        entity: str,
        *,
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_admin_or_superuser(actor)
        schema = self._entity_repo.get_schema(module, entity)
        if schema is None:
            raise NotFoundError(f"Entity '{entity}' in module '{module}' not found")
        return enrich_schema_with_system_fields(schema)

    def create(
        self,
        module: str,
        entity: str,
        schema: dict[str, Any],
        *,
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_superuser(actor)
        if self._entity_repo.entity_exists(module, entity):
            raise ConflictError(f"Entity '{entity}' in module '{module}' already exists")
        candidate = deepcopy(schema)
        validated = self._validator.validate_create_or_update(module, entity, candidate)
        self._entity_repo.create(module, entity, validated)
        return enrich_schema_with_system_fields(validated)

    def update(
        self,
        module: str,
        entity: str,
        schema: dict[str, Any],
        *,
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_superuser(actor)
        current = self._entity_repo.get_schema(module, entity)
        if current is None:
            raise NotFoundError(f"Entity '{entity}' in module '{module}' not found")

        candidate = deepcopy(schema)
        validated = self._validator.validate_create_or_update(module, entity, candidate)
        if module == USER_MODULE and entity == USER_ENTITY:
            self._validate_users_user_protected_fields(current, validated)
        if module == USER_MODULE and entity == GROUP_ENTITY:
            self._validate_users_group_protected_fields(current, validated)
        self._validate_existing_nodes(module, entity, validated)
        self._entity_repo.update(module, entity, validated)
        return enrich_schema_with_system_fields(validated)

    def delete(
        self,
        module: str,
        entity: str,
        *,
        actor: dict[str, Any],
    ) -> None:
        self._require_superuser(actor)
        schema = self._entity_repo.get_schema(module, entity)
        if schema is None:
            raise NotFoundError(f"Entity '{entity}' in module '{module}' not found")

        active_count = self._node_repo.count_active_in_entity(module, entity)
        if active_count > 0:
            raise ConflictError("Entity cannot be deleted while non-deleted nodes exist")

        self._entity_repo.delete(module, entity)
        self._remove_entity_references(module, entity)

    def _validate_existing_nodes(self, module: str, entity: str, candidate_schema: dict[str, Any]) -> None:
        effective_schema = build_effective_node_schema(candidate_schema)
        validator = Draft7Validator(effective_schema, format_checker=FormatChecker())
        for node in self._node_repo.iter_by_entity(module, entity):
            errors = sorted(validator.iter_errors(node), key=lambda e: e.path)
            if errors:
                exc = make_document_validation_error(
                    errors,
                    message=f"Schema update is incompatible with existing node '{node.get('id')}'",
                )
                details = exc.details or {}
                details["node_id"] = node.get("id")
                raise DocumentValidationError(exc.message, details=details)

    def _remove_entity_references(self, module: str, entity: str) -> None:
        module_doc = self._module_repo.get_module(module)
        if isinstance(module_doc, dict):
            root_children = module_doc.get("root_children_entities")
            if isinstance(root_children, list) and entity in root_children:
                self._module_repo.update_module(
                    module,
                    {"root_children_entities": [item for item in root_children if item != entity]},
                )

        docs = self._entity_repo.iter_all()
        for doc in docs:
            schema = doc.get("schema", {})
            changed = False

            children = schema.get("x-meta", {}).get("children", {}).get("entities")
            if isinstance(children, list) and entity in children and doc.get("module") == module:
                schema["x-meta"]["children"]["entities"] = [item for item in children if item != entity]
                changed = True

            props = schema.get("properties", {})
            if isinstance(props, dict):
                if _remove_link_entity_from_properties(props, module, entity):
                    changed = True

            if changed:
                self._entity_repo.replace_schema(doc["_id"], schema)

    def _entity_exists_any(self, module: str, entity: str) -> bool:
        return self._entity_repo.entity_exists(module, entity)

    def _module_exists(self, module: str) -> bool:
        return self._module_repo.module_exists(module)

    def _require_superuser(self, actor: dict[str, Any]) -> None:
        if not actor_has_role_at_least(actor, "superuser"):
            raise AuthorizationError("Only superuser can access entity operations")

    def _require_admin_or_superuser(self, actor: dict[str, Any]) -> None:
        if not actor_has_role_at_least(actor, "admin"):
            raise AuthorizationError("Only admin or superuser can access entity operations")

    def _validate_users_user_protected_fields(
        self,
        current_schema: dict[str, Any],
        candidate_schema: dict[str, Any],
    ) -> None:
        current_properties = current_schema.get("properties", {})
        candidate_properties = candidate_schema.get("properties", {})
        current_required = set(current_schema.get("required", []))
        candidate_required = set(candidate_schema.get("required", []))

        for field in USER_PROTECTED_FIELDS:
            if field not in current_properties:
                continue
            if field not in candidate_properties:
                raise ValidationError(
                    f"Field '{field}' of entity '{USER_ENTITY}' in module '{USER_MODULE}' is immutable"
                )
            if _strip_descriptions(candidate_properties[field]) != _strip_descriptions(current_properties[field]):
                raise ValidationError(
                    f"Field '{field}' of entity '{USER_ENTITY}' in module '{USER_MODULE}' is immutable"
                )
            if (field in candidate_required) != (field in current_required):
                raise ValidationError(
                    f"Field '{field}' required flag of entity '{USER_ENTITY}' in module '{USER_MODULE}' is immutable"
                )

    def _validate_users_group_protected_fields(
        self,
        current_schema: dict[str, Any],
        candidate_schema: dict[str, Any],
    ) -> None:
        current_properties = current_schema.get("properties", {})
        candidate_properties = candidate_schema.get("properties", {})
        current_required = set(current_schema.get("required", []))
        candidate_required = set(candidate_schema.get("required", []))

        for field in GROUP_PROTECTED_FIELDS:
            if field not in current_properties:
                continue
            if field not in candidate_properties:
                raise ValidationError(
                    f"Field '{field}' of entity '{GROUP_ENTITY}' in module '{USER_MODULE}' is immutable"
                )
            if _strip_descriptions(candidate_properties[field]) != _strip_descriptions(current_properties[field]):
                raise ValidationError(
                    f"Field '{field}' of entity '{GROUP_ENTITY}' in module '{USER_MODULE}' is immutable"
                )
            if (field in candidate_required) != (field in current_required):
                raise ValidationError(
                    f"Field '{field}' required flag of entity '{GROUP_ENTITY}' in module '{USER_MODULE}' is immutable"
                )


def _remove_link_entity_from_properties(properties: dict[str, Any], module: str, entity: str) -> bool:
    changed = False
    for field_schema in properties.values():
        if not isinstance(field_schema, dict):
            continue
        candidate = unwrap_nullable(field_schema)

        meta = candidate.get("x-meta", {})
        semantic = meta.get("semantic-type")

        if semantic in {"Link", "LinkArray"}:
            link_meta = meta.get("link")
            if isinstance(link_meta, dict) and link_meta.get("module") == module:
                entities = link_meta.get("entities")
                if isinstance(entities, list) and entity in entities:
                    link_meta["entities"] = [x for x in entities if x != entity]
                    changed = True

        if semantic == "Object":
            nested = candidate.get("properties")
            if isinstance(nested, dict) and _remove_link_entity_from_properties(nested, module, entity):
                changed = True

        if semantic == "Array":
            items = candidate.get("items")
            if isinstance(items, dict):
                nested_props = unwrap_nullable(items).get("properties")
                if isinstance(nested_props, dict) and _remove_link_entity_from_properties(nested_props, module, entity):
                    changed = True

    return changed


def _strip_descriptions(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_descriptions(item)
            for key, item in value.items()
            if key != "description"
        }
    if isinstance(value, list):
        return [_strip_descriptions(item) for item in value]
    return value
