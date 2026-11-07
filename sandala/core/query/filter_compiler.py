from __future__ import annotations

from typing import Any

from sandala.core.errors import QueryValidationError
from sandala.core.query.path_utils import split_field_path
from sandala.core.query.schema_utils import get_field_schema, unwrap_nullable

LOGICAL_KEYS = {"and", "or", "not"}
FILTER_OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "nin", "exists", "size", "regex"}


class FilterCompiler:
    def __init__(self, get_module_schemas, semantic_registry, system_fields):
        self._get_module_schemas = get_module_schemas
        self._semantic_registry = semantic_registry
        self._system_fields = system_fields

    def collect_filter_paths(self, filter_dsl: Any, *, value_only: bool = False) -> set[str]:
        if not isinstance(filter_dsl, dict):
            return set()
        result: set[str] = set()
        for key, value in filter_dsl.items():
            if key in LOGICAL_KEYS:
                if not isinstance(value, list):
                    raise QueryValidationError(f"Logical operator '{key}' must contain an array")
                for item in value:
                    result.update(self.collect_filter_paths(item, value_only=value_only))
            else:
                split_field_path(key)
                # Presence and length do not inspect an object's hidden contents.
                if not value_only or not isinstance(value, dict) or set(value) - {"exists", "size"}:
                    result.add(key)
        return result

    def validate_deleted_filter_restrictions(self, filter_dsl: dict[str, Any]) -> None:
        self._validate_filter_restrictions_recursive(filter_dsl, forbidden_fields={"deleted"})

    def validate_acl_filter_restrictions(self, filter_dsl: dict[str, Any]) -> None:
        self._validate_filter_restrictions_recursive(filter_dsl, forbidden_fields={"perm"})

    def compile_filter(self, filter_dsl: dict[str, Any]) -> dict[str, Any]:
        return self._compile_filter(filter_dsl)

    def build_initial_match(
        self,
        module: str,
        filter_dsl: dict[str, Any],
        scoped_entities: set[str],
        *,
        system_filter: dict[str, Any],
    ) -> dict[str, Any]:
        predicates: list[dict[str, Any]] = [system_filter]

        root_items: list[tuple[str, Any]] = []
        for key, value in filter_dsl.items():
            if key == "and" and isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        root_items.extend((k, v) for k, v in item.items() if k not in LOGICAL_KEYS)
                continue
            if key not in LOGICAL_KEYS:
                root_items.append((key, value))

        for field, expr in root_items:
            if "." in field:
                continue
            if not self._can_filter_before_resolution(module, scoped_entities, field):
                continue
            predicates.append(self._compile_field_predicate(field, expr))

        if not predicates:
            return {}
        if len(predicates) == 1:
            return predicates[0]
        return {"$and": predicates}

    def combine_with_system_filter(
        self,
        compiled_filter: dict[str, Any],
        system_filter: dict[str, Any],
    ) -> dict[str, Any]:
        if not compiled_filter:
            return system_filter
        return {"$and": [system_filter, compiled_filter]}

    def _compile_filter(self, filter_dsl: Any) -> dict[str, Any]:
        if filter_dsl is None:
            return {}
        if not isinstance(filter_dsl, dict):
            raise QueryValidationError("filter must be an object")

        clauses: list[dict[str, Any]] = []
        for key, value in filter_dsl.items():
            if key in LOGICAL_KEYS:
                clauses.append(self._compile_logical(key, value))
                continue
            clauses.append(self._compile_field_predicate(key, value))

        if not clauses:
            return {}
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    def _compile_logical(self, op: str, value: Any) -> dict[str, Any]:
        if not isinstance(value, list) or not value:
            raise QueryValidationError(f"Logical operator '{op}' must contain non-empty array")
        compiled = [self._compile_filter(item) for item in value]
        if op == "and":
            return {"$and": compiled}
        if op == "or":
            return {"$or": compiled}
        return {"$nor": compiled}

    def _validate_filter_restrictions_recursive(
        self,
        filter_dsl: Any,
        *,
        forbidden_fields: set[str],
    ) -> None:
        if not isinstance(filter_dsl, dict):
            raise QueryValidationError("filter must be an object")
        for key, value in filter_dsl.items():
            if key in LOGICAL_KEYS:
                if not isinstance(value, list):
                    raise QueryValidationError(f"Logical operator '{key}' must contain an array")
                for item in value:
                    self._validate_filter_restrictions_recursive(item, forbidden_fields=forbidden_fields)
                continue
            split_field_path(key)
            if key == "deleted" and "deleted" in forbidden_fields:
                raise QueryValidationError("Filtering by deleted field is not allowed")
            if (key == "perm" or key.startswith("perm.")) and "perm" in forbidden_fields:
                raise QueryValidationError("Filtering by ACL fields is not allowed")

    def _compile_field_predicate(self, field: str, value: Any) -> dict[str, Any]:
        split_field_path(field)

        if isinstance(value, dict):
            if not value:
                raise QueryValidationError(f"Filter field '{field}' has empty operator object")
            clauses = []
            for op, operand in value.items():
                if op not in FILTER_OPS:
                    raise QueryValidationError(f"Unsupported filter operator '{op}'")
                clauses.append(self._compile_operator(field, op, operand))
            if len(clauses) == 1:
                return clauses[0]
            return {"$and": clauses}

        return {field: {"$eq": value}}

    def _compile_operator(self, field: str, op: str, operand: Any) -> dict[str, Any]:
        if op in {"in", "nin"} and not isinstance(operand, list):
            raise QueryValidationError(f"Operator '{op}' for field '{field}' requires an array")
        if op == "exists" and not isinstance(operand, bool):
            raise QueryValidationError(f"Operator 'exists' for field '{field}' requires a boolean")
        if op == "size" and (not isinstance(operand, int) or isinstance(operand, bool) or operand < 0):
            raise QueryValidationError(f"Operator 'size' for field '{field}' requires a non-negative integer")
        if op == "regex" and not isinstance(operand, str):
            raise QueryValidationError(f"Operator 'regex' for field '{field}' requires a string")
        mapping = {
            "eq": "$eq",
            "neq": "$ne",
            "gt": "$gt",
            "gte": "$gte",
            "lt": "$lt",
            "lte": "$lte",
            "in": "$in",
            "nin": "$nin",
            "exists": "$exists",
            "size": "$size",
            "regex": "$regex",
        }
        return {field: {mapping[op]: operand}}

    def _can_filter_before_resolution(self, module: str, entities: set[str], field: str) -> bool:
        module_schemas = self._get_module_schemas(module)
        for entity in entities:
            schema = module_schemas.get(entity)
            if not schema:
                continue
            candidate = get_field_schema(schema, field, system_fields=self._system_fields)
            if not candidate:
                continue
            candidate = unwrap_nullable(candidate)
            strategy = self._semantic_registry.strategy_for(candidate)
            behavior = strategy.behavior(candidate)
            if behavior.is_array_container:
                candidate = strategy.child_schema(candidate)
                if candidate is None:
                    return False
                behavior = self._semantic_registry.behavior_for(unwrap_nullable(candidate))
            # Restrict early filtering to scalars and scalar arrays: resolution
            # can replace references anywhere inside an object.
            if behavior.is_reference or behavior.is_container:
                return False
        return True
