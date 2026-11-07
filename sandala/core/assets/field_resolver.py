from __future__ import annotations

from typing import Any

from sandala.core.access import FIELD_ACCESS_MODE_ORDER, normalize_actor_role
from sandala.core.errors import (
    AssetTargetFieldNotFoundError,
    AssetTargetInvalidError,
    FieldWriteForbiddenError,
    NotFoundError,
    ValidationError,
)
from sandala.core.query.schema_utils import unwrap_nullable


def resolve_asset_field(entity_repo, module: str, entity: str, field_path: str) -> dict[str, Any]:
    if not isinstance(field_path, str) or not field_path.strip():
        raise AssetTargetInvalidError("Field 'target.field' must be a non-empty string")
    if "[" in field_path or "]" in field_path:
        raise AssetTargetInvalidError("Field 'target.field' must not use array index syntax")

    entity_schema = entity_repo.get_schema(module, entity)
    if entity_schema is None:
        raise NotFoundError(f"Entity '{entity}' in module '{module}' not found")

    current_schema = entity_schema
    segments = [segment.strip() for segment in field_path.split(".")]
    if any(not segment for segment in segments):
        raise AssetTargetInvalidError("Field 'target.field' contains invalid path segments")

    current_path: list[str] = []
    for idx, segment in enumerate(segments):
        current_path.append(segment)
        current_schema = _descend_array_items(unwrap_nullable(current_schema))
        properties = current_schema.get("properties")
        if not isinstance(properties, dict):
            raise AssetTargetFieldNotFoundError(f"Field '{'.'.join(current_path)}' not found in entity '{entity}'")

        field_schema = properties.get(segment)
        if not isinstance(field_schema, dict):
            raise AssetTargetFieldNotFoundError(f"Field '{'.'.join(current_path)}' not found in entity '{entity}'")

        if idx == len(segments) - 1:
            return _descend_array_items(unwrap_nullable(field_schema))

        semantic = _descend_array_items(unwrap_nullable(field_schema)).get("x-meta", {}).get("semantic-type")
        if semantic != "Object":
            raise ValidationError(f"Field '{'.'.join(current_path)}' is not an object container")
        current_schema = field_schema

    raise AssetTargetFieldNotFoundError(f"Field '{field_path}' not found in entity '{entity}'")


def enforce_field_write_access(field_schema: dict[str, Any], field_path: str, *, actor: dict[str, Any] | None) -> None:
    write_mode = field_schema.get("x-meta", {}).get("write-mode")
    if not isinstance(write_mode, str):
        raise ValidationError(f"Field '{field_path}' has invalid write-mode")
    actor_level = FIELD_ACCESS_MODE_ORDER[normalize_actor_role(actor)]
    required_level = FIELD_ACCESS_MODE_ORDER.get(write_mode)
    if required_level is None:
        raise ValidationError(f"Field '{field_path}' has invalid write-mode")
    if actor_level < required_level:
        raise FieldWriteForbiddenError(f"Field '{field_path}' is not writable for current actor")


def _descend_array_items(field_schema: dict[str, Any]) -> dict[str, Any]:
    if field_schema.get("x-meta", {}).get("semantic-type") != "Array":
        return field_schema
    items = field_schema.get("items")
    if not isinstance(items, dict):
        raise ValidationError("Array field has invalid items schema")
    return unwrap_nullable(items)
