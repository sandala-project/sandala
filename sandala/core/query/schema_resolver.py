from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sandala.core.access import FIELD_ACCESS_MODE_ORDER
from sandala.core.errors import QueryValidationError
from sandala.core.query.path_utils import split_field_path
from sandala.core.query.schema_utils import get_field_schema, unwrap_nullable
from sandala.core.query.semantic_registry import (
    FieldBehavior,
    ReferenceTarget,
    SemanticRegistry,
)
from sandala.core.query.system_fields import SystemFieldProvider

@dataclass(frozen=True)
class ResolveContext:
    module: str
    entity: str
    schema_node: dict[str, Any]
    is_node_root: bool = True


@dataclass(frozen=True)
class SegmentResolution:
    path: tuple[str, ...]
    behavior: FieldBehavior
    target: ReferenceTarget | None
    next_contexts: list[ResolveContext]


class SchemaPathResolver:
    def __init__(self, get_module_schemas, semantic_registry: SemanticRegistry, system_fields: SystemFieldProvider):
        self._get_module_schemas = get_module_schemas
        self._registry = semantic_registry
        self._system_fields = system_fields

    def validate_stored_paths(self, module: str, entities: frozenset[str], paths: set[str]) -> None:
        module_schemas = self._get_module_schemas(module)
        for path in paths:
            parts = split_field_path(path)
            for entity in entities:
                schema = module_schemas.get(entity)
                if schema is None:
                    continue
                for index, part in enumerate(parts):
                    field = get_field_schema(
                        schema,
                        part,
                        system_fields=self._system_fields if index == 0 else None,
                    )
                    if field is None:
                        break
                    field = unwrap_nullable(field)
                    if index == len(parts) - 1:
                        break
                    behavior = self._registry.behavior_for(field)
                    if behavior.is_reference:
                        raise QueryValidationError(
                            f"Required filter cannot traverse link '{'.'.join(parts[:index + 1])}'"
                        )
                    child = self._registry.strategy_for(field).child_schema(field)
                    if child is None:
                        raise QueryValidationError(
                            f"Required filter cannot traverse non-container field '{'.'.join(parts[:index + 1])}'"
                        )
                    schema = unwrap_nullable(child)

    def resolve_segment(
        self,
        contexts: list[ResolveContext],
        *,
        segment: str,
        prefix: tuple[str, ...],
        actor_level: int,
        has_descent: bool = True,
        inspect_contents: bool = False,
    ) -> SegmentResolution:
        field_defs = self._collect_field_defs(contexts, segment)
        if not field_defs:
            raise QueryValidationError(f"Field '{'.'.join((*prefix, segment))}' not found")

        full_path = (*prefix, segment)
        path_label = ".".join(full_path)
        self._ensure_visible(path_label, field_defs, actor_level)
        if inspect_contents:
            self._ensure_stored_content_visible(path_label, field_defs, actor_level)

        behavior = self._resolve_behavior(path_label, field_defs, strict_reference_collision=has_descent)
        if behavior.is_array_container and has_descent:
            item_defs = [
                (ctx, unwrap_nullable(child))
                for ctx, field in field_defs
                if (child := self._registry.strategy_for(field).child_schema(field)) is not None
            ]
            if item_defs:
                self._resolve_behavior(path_label, item_defs, strict_reference_collision=True)
        # Terminal paths use stored values, independently of reference targets.
        target = self._resolve_target(full_path, field_defs, behavior) if has_descent else None

        if behavior.is_reference:
            next_contexts = self._contexts_for_target(target) if target is not None else []
        elif behavior.is_container:
            next_contexts = self._contexts_for_children(field_defs)
        else:
            next_contexts = []

        return SegmentResolution(
            path=full_path,
            behavior=behavior,
            target=target,
            next_contexts=next_contexts,
        )

    def _collect_field_defs(
        self,
        contexts: list[ResolveContext],
        field_name: str,
    ) -> list[tuple[ResolveContext, dict[str, Any]]]:
        field_defs: list[tuple[ResolveContext, dict[str, Any]]] = []
        system_spec = self._system_fields.get(field_name)

        for ctx in contexts:
            field_schema = get_field_schema(ctx.schema_node, field_name)
            if field_schema is not None:
                field_defs.append((ctx, unwrap_nullable(field_schema)))
            elif system_spec is not None and ctx.is_node_root:
                field_defs.append((ctx, system_spec.synthetic_schema))

        return field_defs

    def _resolve_behavior(
        self,
        path_label: str,
        field_defs: list[tuple[ResolveContext, dict[str, Any]]],
        *,
        strict_reference_collision: bool,
    ) -> FieldBehavior:
        behaviors = [self._registry.behavior_for(field) for _, field in field_defs]
        first = behaviors[0]
        if not strict_reference_collision:
            return first

        has_reference = any(behavior.is_reference for behavior in behaviors)
        has_non_reference = any(not behavior.is_reference for behavior in behaviors)
        if strict_reference_collision and has_reference and has_non_reference:
            raise QueryValidationError(f"Field collision at path segment '{path_label}'")

        reference_kinds = {(behavior.semantic_type, behavior.is_multi_reference) for behavior in behaviors if behavior.is_reference}
        if strict_reference_collision and len(reference_kinds) > 1:
            raise QueryValidationError(f"Link type collision at path segment '{path_label}'")

        for behavior in behaviors[1:]:
            if behavior.is_array_container != first.is_array_container or (
                behavior.semantic_type != first.semantic_type and not (behavior.is_container and first.is_container)
            ):
                raise QueryValidationError(f"Field collision at path segment '{path_label}'")
        return first

    def _resolve_target(
        self,
        path: tuple[str, ...],
        field_defs: list[tuple[ResolveContext, dict[str, Any]]],
        behavior: FieldBehavior,
    ) -> ReferenceTarget | None:
        if not behavior.is_reference:
            return None

        targets: list[ReferenceTarget] = []
        entities_by_source: dict[str, tuple[str, ...]] = {}
        for ctx, field in field_defs:
            strategy = self._registry.strategy_for(field)
            target = strategy.reference_target(
                module=ctx.module,
                entity=ctx.entity,
                field_path=path,
                field_schema=field,
            )
            if target is not None:
                targets.append(target)
                entities_by_source[ctx.entity] = tuple(sorted(set(target.entities)))

        if not targets:
            raise QueryValidationError(f"Link module collision at path '{'.'.join(path)}'")

        modules = {target.module for target in targets}
        if len(modules) != 1:
            raise QueryValidationError(f"Link module collision at path '{'.'.join(path)}'")
        scope_modes = {target.entity_scope_mode for target in targets}
        if len(scope_modes) != 1:
            raise QueryValidationError(f"Reference scope collision at path '{'.'.join(path)}'")
        entities: set[str] = set()
        for target in targets:
            entities.update(target.entities)
        scope_mode = next(iter(scope_modes))
        source_scopes = ()
        if scope_mode == "explicit" and len(set(entities_by_source.values())) > 1:
            source_scopes = tuple(sorted(entities_by_source.items()))
        return ReferenceTarget(
            entity_scope_mode=scope_mode,
            module=next(iter(modules)),
            entities=tuple(sorted(entities)),
            entities_by_source=source_scopes,
        )

    def _contexts_for_children(
        self,
        field_defs: list[tuple[ResolveContext, dict[str, Any]]],
    ) -> list[ResolveContext]:
        next_contexts: list[ResolveContext] = []
        for ctx, field in field_defs:
            strategy = self._registry.strategy_for(field)
            child = strategy.child_schema(field)
            if isinstance(child, dict):
                next_contexts.append(ResolveContext(
                    module=ctx.module, entity=ctx.entity, schema_node=unwrap_nullable(child), is_node_root=False,
                ))
        return next_contexts

    def _contexts_for_target(self, target: ReferenceTarget) -> list[ResolveContext]:
        if not target.module:
            return []
        if not target.entities and target.entity_scope_mode != "all_module":
            return []
        module_schemas = self._get_module_schemas(target.module)
        entity_names = target.entities or tuple(sorted(module_schemas.keys()))
        contexts: list[ResolveContext] = []
        for entity_name in entity_names:
            schema = module_schemas.get(entity_name)
            if isinstance(schema, dict):
                contexts.append(ResolveContext(module=target.module, entity=entity_name, schema_node=schema))
        return contexts

    def _ensure_visible(
        self,
        path_label: str,
        field_defs: list[tuple[ResolveContext, dict[str, Any]]],
        actor_level: int,
        *,
        contents: bool = False,
    ) -> None:
        for _, field in field_defs:
            visibility_mode = field.get("x-meta", {}).get("visibility-mode")
            field_level = FIELD_ACCESS_MODE_ORDER.get(visibility_mode, FIELD_ACCESS_MODE_ORDER["all"])
            if actor_level < field_level:
                if contents:
                    raise QueryValidationError(f"Field '{path_label}' has contents that are not visible for current user")
                raise QueryValidationError(f"Field '{path_label}' is not visible for current user")

    def _ensure_stored_content_visible(
        self,
        path_label: str,
        field_defs: list[tuple[ResolveContext, dict[str, Any]]],
        actor_level: int,
    ) -> None:
        # Compare/sort the stored container only when its entire value is visible.
        # References are stored IDs, so this walk never loads their target schemas.
        for ctx, field in field_defs:
            child = self._registry.strategy_for(field).child_schema(field)
            if child is None:
                continue
            child = unwrap_nullable(child)
            self._ensure_visible(path_label, [(ctx, child)], actor_level, contents=True)
            for descendant in child.get("properties", {}).values():
                descendants = [(ctx, unwrap_nullable(descendant))]
                self._ensure_visible(path_label, descendants, actor_level, contents=True)
                self._ensure_stored_content_visible(path_label, descendants, actor_level)
