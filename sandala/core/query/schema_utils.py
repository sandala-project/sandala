from __future__ import annotations

from typing import Any


def get_field_schema(
    schema_node: dict[str, Any],
    field_name: str,
    *,
    system_fields: Any | None = None,
) -> dict[str, Any] | None:
    properties = schema_node.get("properties")
    if isinstance(properties, dict):
        field = properties.get(field_name)
        if isinstance(field, dict):
            return field

    if system_fields is not None:
        system_spec = system_fields.get(field_name)
        if system_spec is not None:
            return system_spec.synthetic_schema

    return None


def unwrap_nullable(schema: dict[str, Any]) -> dict[str, Any]:
    any_of = schema.get("anyOf") if isinstance(schema, dict) else None
    if not isinstance(any_of, list):
        return schema
    for variant in any_of:
        if isinstance(variant, dict) and variant.get("type") != "null":
            return variant
    return schema
