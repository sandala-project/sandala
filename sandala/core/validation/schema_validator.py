from __future__ import annotations

from copy import deepcopy
from typing import Any

from jsonschema import Draft7Validator, FormatChecker

from sandala.core.access import FIELD_ACCESS_MODE_ORDER
from sandala.core.errors import SchemaValidationError, ValidationError
from sandala.core.validation.error_normalizer import make_schema_validation_error

SYSTEM_FIELDS = [
    "id",
    "entity",
    "parent",
    "owner",
    "group",
    "perm",
    "depth",
    "ancestors",
    "deleted",
    "cdate",
    "mdate",
]
SYSTEM_FIELD_SET = set(SYSTEM_FIELDS)

SYSTEM_PROPERTIES: dict[str, dict[str, Any]] = {
    "id": {"type": "string", "format": "uuid"},
    "entity": {"type": "string"},
    "parent": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    "owner": {"type": "string", "format": "uuid"},
    "group": {"type": "string", "format": "uuid"},
    "perm": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "owner": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "r": {"type": "boolean"},
                    "w": {"type": "boolean"},
                    "p": {"type": "boolean"},
                },
                "required": ["r", "w", "p"],
            },
            "group": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "r": {"type": "boolean"},
                    "w": {"type": "boolean"},
                    "p": {"type": "boolean"},
                },
                "required": ["r", "w", "p"],
            },
            "others": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "r": {"type": "boolean"},
                    "w": {"type": "boolean"},
                    "p": {"type": "boolean"},
                },
                "required": ["r", "w", "p"],
            },
        },
        "required": ["owner", "group", "others"],
    },
    "depth": {"type": "integer", "minimum": 0},
    "ancestors": {"type": "array", "items": {"type": "string"}},
    "deleted": {"type": "boolean"},
    "cdate": {"type": "string", "format": "date-time"},
    "mdate": {"type": "string", "format": "date-time"},
}

_META_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "properties", "additionalProperties", "x-meta"],
    "properties": {
        "$schema": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "x-ui": {"$ref": "#/definitions/root_ui"},
        "type": {"const": "object"},
        "additionalProperties": {"const": False},
        "required": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": True,
        },
        "properties": {
            "type": "object",
            "propertyNames": {
                "allOf": [
                    {"$ref": "#/definitions/field_name"},
                    {"not": {"enum": ["_id", "and", "or", "not"]}},
                ],
            },
            "additionalProperties": {"$ref": "#/definitions/field_schema"},
        },
        "x-meta": {"$ref": "#/definitions/root_meta"},
    },
    "definitions": {
        "field_name": {
            "type": "string",
            "minLength": 1,
            "not": {"pattern": r"[.*\u0000]|^(?:\$|__sandala_)"},
        },
        "access_mode": {"enum": ["all", "admin", "superuser", "none"]},
        "x_meta_base": {
            "type": "object",
            "additionalProperties": False,
            "required": ["semantic-type", "visibility-mode", "write-mode"],
            "properties": {
                "semantic-type": {
                    "enum": [
                        "String",
                        "Password",
                        "Text",
                        "RichText",
                        "Number",
                        "Integer",
                        "Boolean",
                        "Date",
                        "DateTime",
                        "File",
                        "Image",
                        "Video",
                        "Array",
                        "Object",
                        "Link",
                        "LinkArray",
                    ]
                },
                "visibility-mode": {"$ref": "#/definitions/access_mode"},
                "write-mode": {"$ref": "#/definitions/access_mode"},
                "link": {"$ref": "#/definitions/link_meta"},
            },
        },
        "link_meta": {
            "type": "object",
            "additionalProperties": False,
            "required": ["module", "entities"],
            "properties": {
                "module": {"type": "string", "minLength": 1},
                "entities": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "field_schema": {
            "type": "object",
            "oneOf": [
                {"$ref": "#/definitions/non_null_field"},
                {"$ref": "#/definitions/nullable_field"},
            ],
        },
        "array_item_constraints": {
            "properties": {
                "x-meta": {
                    "properties": {
                        "semantic-type": {"not": {"enum": ["Array", "Link", "LinkArray"]}},
                    },
                },
                "anyOf": {
                    "items": {"$ref": "#/definitions/array_item_constraints"},
                },
            },
        },
        "nullable_field": {
            "type": "object",
            "additionalProperties": False,
            "required": ["anyOf"],
            "properties": {
                "anyOf": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "allOf": [
                        {"contains": {"$ref": "#/definitions/non_null_field"}},
                        {
                            "contains": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["type"],
                                "properties": {"type": {"const": "null"}},
                            }
                        },
                    ],
                }
            },
        },
        "non_null_field": {
            "type": "object",
            "oneOf": [
                {"$ref": "#/definitions/semantic_string"},
                {"$ref": "#/definitions/semantic_password"},
                {"$ref": "#/definitions/semantic_text"},
                {"$ref": "#/definitions/semantic_rich_text"},
                {"$ref": "#/definitions/semantic_number"},
                {"$ref": "#/definitions/semantic_integer"},
                {"$ref": "#/definitions/semantic_boolean"},
                {"$ref": "#/definitions/semantic_date"},
                {"$ref": "#/definitions/semantic_datetime"},
                {"$ref": "#/definitions/semantic_file"},
                {"$ref": "#/definitions/semantic_image"},
                {"$ref": "#/definitions/semantic_video"},
                {"$ref": "#/definitions/semantic_array"},
                {"$ref": "#/definitions/semantic_object"},
                {"$ref": "#/definitions/semantic_link"},
                {"$ref": "#/definitions/semantic_link_array"},
            ],
        },
        "semantic_string": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "string"},
                "pattern": {"type": "string"},
                "enum": {"type": "array"},
                "minLength": {"type": "integer", "minimum": 0},
                "maxLength": {"type": "integer", "minimum": 0},
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "String"}}},
                    ]
                },
            },
        },
        "semantic_password": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "string"},
                "pattern": {"type": "string"},
                "minLength": {"type": "integer", "minimum": 0},
                "maxLength": {"type": "integer", "minimum": 0},
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "Password"}}},
                    ]
                },
            },
        },
        "semantic_text": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "string"},
                "pattern": {"type": "string"},
                "minLength": {"type": "integer", "minimum": 0},
                "maxLength": {"type": "integer", "minimum": 0},
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "Text"}}},
                    ]
                },
            },
        },
        "semantic_rich_text": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "string"},
                "pattern": {"type": "string"},
                "minLength": {"type": "integer", "minimum": 0},
                "maxLength": {"type": "integer", "minimum": 0},
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "RichText"}}},
                    ]
                },
            },
        },
        "semantic_number": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "number"},
                "minimum": {"type": "number"},
                "maximum": {"type": "number"},
                "exclusiveMinimum": {"type": "number"},
                "exclusiveMaximum": {"type": "number"},
                "multipleOf": {"type": "number", "exclusiveMinimum": 0},
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "Number"}}},
                    ]
                },
            },
        },
        "semantic_integer": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "integer"},
                "minimum": {"type": "integer"},
                "maximum": {"type": "integer"},
                "exclusiveMinimum": {"type": "integer"},
                "exclusiveMaximum": {"type": "integer"},
                "multipleOf": {"type": "integer", "minimum": 1},
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "Integer"}}},
                    ]
                },
            },
        },
        "semantic_boolean": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "boolean"},
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "Boolean"}}},
                    ]
                },
            },
        },
        "semantic_date": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "format", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "string"},
                "format": {"const": "date"},
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "Date"}}},
                    ]
                },
            },
        },
        "semantic_datetime": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "format", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "string"},
                "format": {"const": "date-time"},
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "DateTime"}}},
                    ]
                },
            },
        },
        "semantic_file": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "properties", "required", "additionalProperties", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "object"},
                "additionalProperties": {"const": False},
                "properties": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["url"],
                    "properties": {
                        "url": {"type": "object", "additionalProperties": False, "required": ["type"], "properties": {"type": {"const": "string"}}},
                        "mime-type": {"type": "object", "additionalProperties": False, "required": ["type"], "properties": {"type": {"const": "string"}}},
                        "size": {"type": "object", "additionalProperties": False, "required": ["type"], "properties": {"type": {"const": "integer"}}},
                    },
                },
                "required": {
                    "allOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"contains": {"const": "url"}},
                    ]
                },
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "File"}}},
                    ]
                },
            },
        },
        "semantic_image": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "properties", "required", "additionalProperties", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "object"},
                "additionalProperties": {"const": False},
                "properties": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["url", "mime-type", "width", "height", "size"],
                    "properties": {
                        "url": {"type": "object", "additionalProperties": False, "required": ["type"], "properties": {"type": {"const": "string"}}},
                        "mime-type": {"type": "object", "additionalProperties": False, "required": ["type"], "properties": {"type": {"const": "string"}}},
                        "width": {"type": "object", "additionalProperties": False, "required": ["type"], "properties": {"type": {"const": "integer"}}},
                        "height": {"type": "object", "additionalProperties": False, "required": ["type"], "properties": {"type": {"const": "integer"}}},
                        "size": {"type": "object", "additionalProperties": False, "required": ["type"], "properties": {"type": {"const": "integer"}}},
                    },
                },
                "required": {
                    "allOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"contains": {"const": "url"}},
                    ]
                },
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "Image"}}},
                    ]
                },
            },
        },
        "semantic_video": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "properties", "required", "additionalProperties", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "object"},
                "additionalProperties": {"const": False},
                "properties": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["url", "mime-type", "size"],
                    "properties": {
                        "url": {"type": "object", "additionalProperties": False, "required": ["type"], "properties": {"type": {"const": "string"}}},
                        "mime-type": {"type": "object", "additionalProperties": False, "required": ["type"], "properties": {"type": {"const": "string"}}},
                        "size": {"type": "object", "additionalProperties": False, "required": ["type"], "properties": {"type": {"const": "integer"}}},
                    },
                },
                "required": {
                    "allOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"contains": {"const": "url"}},
                    ]
                },
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "Video"}}},
                    ]
                },
            },
        },
        "semantic_object": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "properties", "additionalProperties", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "object"},
                "additionalProperties": {"const": False},
                "properties": {
                    "type": "object",
                    "propertyNames": {"$ref": "#/definitions/field_name"},
                    "additionalProperties": {"$ref": "#/definitions/field_schema"},
                },
                "required": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "Object"}}},
                    ]
                },
            },
        },
        "semantic_array": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "items", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "array"},
                "items": {
                    "allOf": [
                        {"$ref": "#/definitions/field_schema"},
                        {"$ref": "#/definitions/array_item_constraints"},
                    ],
                },
                "minItems": {"type": "integer", "minimum": 0},
                "maxItems": {"type": "integer", "minimum": 0},
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {"properties": {"semantic-type": {"const": "Array"}}},
                    ]
                },
            },
        },
        "semantic_link": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "format", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "string"},
                "format": {"const": "uuid"},
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {
                            "type": "object",
                            "required": ["link"],
                            "properties": {
                                "semantic-type": {"const": "Link"},
                                "link": {"$ref": "#/definitions/link_meta"},
                            }
                        },
                    ]
                },
            },
        },
        "semantic_link_array": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "items", "x-meta"],
            "properties": {
                "description": {"type": "string"},
                "type": {"const": "array"},
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["type", "format"],
                    "properties": {
                        "type": {"const": "string"},
                        "format": {"const": "uuid"},
                    },
                },
                "minItems": {"type": "integer", "minimum": 0},
                "maxItems": {"type": "integer", "minimum": 0},
                "x-meta": {
                    "allOf": [
                        {"$ref": "#/definitions/x_meta_base"},
                        {
                            "type": "object",
                            "required": ["link"],
                            "properties": {
                                "semantic-type": {"const": "LinkArray"},
                                "link": {"$ref": "#/definitions/link_meta"},
                            }
                        },
                    ]
                },
            },
        },
        "perm_section": {
            "type": "object",
            "additionalProperties": False,
            "required": ["r", "w", "p"],
            "properties": {
                "r": {"type": "boolean"},
                "w": {"type": "boolean"},
                "p": {"type": "boolean"},
            },
        },
        "perm_value": {
            "type": "object",
            "additionalProperties": False,
            "required": ["owner", "group", "others"],
            "properties": {
                "owner": {"$ref": "#/definitions/perm_section"},
                "group": {"$ref": "#/definitions/perm_section"},
                "others": {"$ref": "#/definitions/perm_section"},
            },
        },
        "root_meta": {
            "type": "object",
            "additionalProperties": False,
            "required": ["children", "perm"],
            "properties": {
                "children": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["entities"],
                    "properties": {
                        "entities": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "perm": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["default"],
                    "properties": {
                        "default": {"$ref": "#/definitions/perm_value"},
                    },
                },
            },
        },
        "root_ui": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "labels": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "tree": {"type": "string"},
                        "reference": {"type": "string"},
                    },
                },
            },
        },
    },
}


class EntitySchemaValidator:
    def __init__(self, entity_exists: callable, module_exists: callable):
        self._entity_exists = entity_exists
        self._module_exists = module_exists
        self._structural_validator = Draft7Validator(_META_SCHEMA, format_checker=FormatChecker())

    def validate_create_or_update(self, module: str, entity: str, schema: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(schema, dict):
            raise SchemaValidationError("Schema must be an object")

        self._validate_structural_schema(_without_system_fields(schema))

        schema["title"] = entity

        properties = schema["properties"]
        required = schema.get("required", [])

        self._validate_system_fields_contract(properties, required)

        user_properties = {k: v for k, v in properties.items() if k not in SYSTEM_FIELD_SET}
        user_required = [field for field in required if field not in SYSTEM_FIELD_SET]

        x_meta = deepcopy(schema["x-meta"])
        self._validate_required_password_fields("", user_properties, user_required)
        self._validate_field_context(module, user_properties)
        self._validate_children_entities(module, x_meta)

        normalized = deepcopy(schema)
        normalized["properties"] = user_properties
        normalized["required"] = user_required
        normalized["x-meta"] = deepcopy(x_meta)
        return normalized

    def _validate_structural_schema(self, schema: dict[str, Any]) -> None:
        errors = sorted(self._structural_validator.iter_errors(schema), key=lambda e: list(e.path))
        if not errors:
            return
        raise make_schema_validation_error(errors, message="Invalid schema")

    def _validate_children_entities(self, module: str, x_meta: dict[str, Any]) -> None:
        children_entities = x_meta["children"]["entities"]
        for child in children_entities:
            if not self._entity_exists(module, child):
                raise ValidationError(f"Unknown child entity '{child}' in module '{module}'")

    def _validate_system_fields_contract(self, properties: dict[str, Any], required: list[Any]) -> None:
        sys_in_props = SYSTEM_FIELD_SET.intersection(properties.keys())
        sys_in_required = SYSTEM_FIELD_SET.intersection(required)

        if sys_in_props and sys_in_props != SYSTEM_FIELD_SET:
            missing = sorted(SYSTEM_FIELD_SET - sys_in_props)
            raise ValidationError(
                f"If system fields are provided in properties, all system fields must be present. Missing: {missing}"
            )

        if sys_in_required and sys_in_required != SYSTEM_FIELD_SET:
            missing = sorted(SYSTEM_FIELD_SET - sys_in_required)
            raise ValidationError(
                f"If system fields are provided in required, all system fields must be present. Missing: {missing}"
            )

        if bool(sys_in_props) != bool(sys_in_required):
            raise ValidationError(
                "System fields in properties and required must be provided together (all-or-none in both places)"
            )

        if sys_in_props:
            for field, expected in SYSTEM_PROPERTIES.items():
                candidate = properties.get(field)
                if candidate != expected:
                    raise ValidationError(
                        f"System field '{field}' has invalid schema. Expected exactly: {expected}"
                    )

    def _validate_field_context(self, module: str, properties: dict[str, Any]) -> None:
        for field_name, field_schema in properties.items():
            self._validate_field_context_recursive(
                module,
                field_name,
                field_schema,
                parent_visibility_mode=None,
                parent_write_mode=None,
            )

    def _validate_field_context_recursive(
        self,
        module: str,
        field_name: str,
        field_schema: dict[str, Any],
        *,
        parent_visibility_mode: str | None,
        parent_write_mode: str | None,
    ) -> None:
        schema = _extract_non_null_schema(field_name, field_schema)
        meta = schema["x-meta"]
        visibility_mode = meta["visibility-mode"]
        write_mode = meta["write-mode"]

        if parent_visibility_mode is not None and FIELD_ACCESS_MODE_ORDER[visibility_mode] < FIELD_ACCESS_MODE_ORDER[parent_visibility_mode]:
            raise ValidationError(
                f"Field '{field_name}' x-meta.visibility-mode cannot be wider than parent mode '{parent_visibility_mode}'"
            )
        if parent_write_mode is not None and FIELD_ACCESS_MODE_ORDER[write_mode] < FIELD_ACCESS_MODE_ORDER[parent_write_mode]:
            raise ValidationError(
                f"Field '{field_name}' x-meta.write-mode cannot be wider than parent mode '{parent_write_mode}'"
            )

        semantic = meta.get("semantic-type")

        if semantic in {"Link", "LinkArray"}:
            link_meta = meta["link"]
            module_name = link_meta["module"]
            entities = link_meta["entities"]
            if not self._module_exists(module_name):
                raise ValidationError(f"Field '{field_name}' references unknown module '{module_name}'")
            for linked_entity in entities:
                if not self._entity_exists(module_name, linked_entity):
                    raise ValidationError(
                        f"Field '{field_name}' references unknown entity '{linked_entity}' in module '{module_name}'"
                    )

        if semantic == "Object":
            nested = schema["properties"]
            required = schema.get("required", [])
            for required_item in required:
                if required_item not in nested:
                    raise ValidationError(
                        f"Field '{field_name}' Object required contains unknown property '{required_item}'"
                    )
            self._validate_required_password_fields(field_name, nested, required)
            for nested_name, nested_schema in nested.items():
                self._validate_field_context_recursive(
                    module,
                    f"{field_name}.{nested_name}",
                    nested_schema,
                    parent_visibility_mode=visibility_mode,
                    parent_write_mode=write_mode,
                )

        if semantic == "Array":
            items = schema["items"]
            item_schema = _extract_non_null_schema(f"{field_name}[]", items)
            item_meta = item_schema["x-meta"]

            if item_meta["visibility-mode"] != visibility_mode:
                raise ValidationError(
                    f"Field '{field_name}' Array items x-meta.visibility-mode must match Array visibility-mode"
                )
            if item_meta["write-mode"] != write_mode:
                raise ValidationError(
                    f"Field '{field_name}' Array items x-meta.write-mode must match Array write-mode"
                )

            self._validate_field_context_recursive(
                module,
                f"{field_name}[]",
                items,
                parent_visibility_mode=visibility_mode,
                parent_write_mode=write_mode,
            )

    def _validate_required_password_fields(
        self,
        parent_path: str,
        properties: dict[str, Any],
        required: list[Any],
    ) -> None:
        for field_name in required:
            field_schema = properties.get(field_name)
            if not isinstance(field_name, str) or not isinstance(field_schema, dict):
                continue
            if not _is_password_only_field(field_schema):
                continue
            path = f"{parent_path}.{field_name}" if parent_path else field_name
            raise ValidationError(
                f"Field '{path}' with semantic type Password cannot be required"
            )


def _extract_non_null_schema(field_name: str, field_schema: dict[str, Any]) -> dict[str, Any]:
    any_of = field_schema.get("anyOf")
    if any_of is None:
        return field_schema
    for variant in any_of:
        if variant.get("type") == "null":
            continue
        return variant
    # Structural validation guarantees this path is unreachable.
    raise ValidationError(f"Field '{field_name}' anyOf does not contain non-null schema")


def _is_password_only_field(field_schema: dict[str, Any]) -> bool:
    schema = _extract_non_null_schema("field", field_schema)
    meta = schema.get("x-meta")
    semantic_type = meta.get("semantic-type") if isinstance(meta, dict) else None
    if semantic_type == "Password":
        return True
    if semantic_type != "Array":
        return False
    items = schema.get("items")
    if not isinstance(items, dict):
        return False
    item_schema = _extract_non_null_schema("field[]", items)
    return item_schema.get("x-meta", {}).get("semantic-type") == "Password"


def _without_system_fields(schema: dict[str, Any]) -> dict[str, Any]:
    candidate = deepcopy(schema)
    properties = candidate.get("properties")
    required = candidate.get("required")
    if isinstance(properties, dict):
        candidate["properties"] = {
            key: value for key, value in properties.items() if key not in SYSTEM_FIELD_SET
        }
    if isinstance(required, list):
        candidate["required"] = [key for key in required if key not in SYSTEM_FIELD_SET]
    return candidate


def enrich_schema_with_system_fields(entity_schema: dict[str, Any]) -> dict[str, Any]:
    schema = deepcopy(entity_schema)
    properties = dict(schema.get("properties", {}))
    required = list(schema.get("required", []))

    for field in SYSTEM_FIELDS:
        properties[field] = deepcopy(SYSTEM_PROPERTIES[field])
        if field not in required:
            required.append(field)

    schema["properties"] = properties
    schema["required"] = required
    return schema


def build_effective_node_schema(entity_schema: dict[str, Any]) -> dict[str, Any]:
    """Produce full node JSON Schema with system fields for runtime validation."""
    return enrich_schema_with_system_fields(entity_schema)
