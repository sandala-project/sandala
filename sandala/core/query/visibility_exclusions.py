from __future__ import annotations

from typing import Any

from sandala.core.access import FIELD_ACCESS_MODE_ORDER
from sandala.core.query.schema_resolver import ResolveContext
from sandala.core.query.schema_utils import get_field_schema, unwrap_nullable


class VisibilityExclusionsCollector:
    def __init__(self, get_module_schemas, semantic_registry):
        self._get_module_schemas = get_module_schemas
        self._semantic_registry = semantic_registry

    def collect(
        self,
        module: str,
        entities: set[str],
        *,
        actor_level: int,
    ) -> set[str]:
        contexts = self._root_contexts(module, entities)
        return self._collect_hidden_descendants(contexts, actor_level)

    def _root_contexts(self, module: str, entities: set[str]) -> list[ResolveContext]:
        module_schemas = self._get_module_schemas(module)
        contexts: list[ResolveContext] = []
        for entity in entities:
            schema = module_schemas.get(entity)
            if isinstance(schema, dict):
                contexts.append(ResolveContext(module=module, entity=entity, schema_node=schema))
        return contexts

    def _collect_hidden_descendants(self, contexts: list[ResolveContext], actor_level: int) -> set[str]:
        hidden: set[str] = set()
        if not contexts:
            return hidden

        field_names: set[str] = set()
        for ctx in contexts:
            properties = ctx.schema_node.get("properties")
            if isinstance(properties, dict):
                field_names.update(properties.keys())

        for field_name in sorted(field_names):
            field_defs: list[tuple[ResolveContext, dict[str, Any]]] = []
            for ctx in contexts:
                field = get_field_schema(ctx.schema_node, field_name)
                if field is not None:
                    field_defs.append((ctx, unwrap_nullable(field)))

            if not field_defs:
                continue

            if any(not self._is_visible_for_actor(field, actor_level) for _, field in field_defs):
                hidden.add(field_name)
                continue

            child_contexts: list[ResolveContext] = []
            for ctx, field in field_defs:
                # References have no child schema here: their targets are
                # sanitized in their own lookup scope.
                child_schema = self._semantic_registry.strategy_for(field).child_schema(field)
                if isinstance(child_schema, dict):
                    child_contexts.append(ResolveContext(module=ctx.module, entity=ctx.entity, schema_node=unwrap_nullable(child_schema)))

            for child in self._collect_hidden_descendants(child_contexts, actor_level):
                hidden.add(f"{field_name}.{child}")

        return hidden

    def _is_visible_for_actor(self, field_schema: dict[str, Any], actor_level: int) -> bool:
        visibility_mode = field_schema.get("x-meta", {}).get("visibility-mode")
        level = FIELD_ACCESS_MODE_ORDER.get(visibility_mode, FIELD_ACCESS_MODE_ORDER["all"])
        return actor_level >= level
