from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sandala.core.errors import QueryValidationError
from sandala.core.query.path_utils import split_field_path
from sandala.core.query.schema_resolver import ResolveContext, SchemaPathResolver


@dataclass
class LookupPlanNode:
    path: str
    is_multi_link: bool
    link_module: str
    link_entities: tuple[str, ...]
    entities_by_source: tuple[tuple[str, tuple[str, ...]], ...] = ()
    # Ordered array paths in this lookup's source document. Arrays outside a
    # parent lookup are not included.
    array_ancestors: tuple[str, ...] = ()
    children: dict[str, "LookupPlanNode"] = field(default_factory=dict)


class LookupPlanner:
    def __init__(self, get_module_schemas, schema_resolver: SchemaPathResolver):
        self._get_module_schemas = get_module_schemas
        self._schema_resolver = schema_resolver

    def plan(
        self,
        module: str,
        scoped_entities: set[str],
        input_paths: list[str],
        *,
        actor_level: int,
        value_paths: set[str] | None = None,
    ) -> list[LookupPlanNode]:
        segmented = [split_field_path(path, allow_wildcard=True) for path in input_paths if path != "*"]
        if not scoped_entities or not input_paths:
            return []

        module_schemas = self._get_module_schemas(module)
        contexts = [
            ResolveContext(module=module, entity=entity, schema_node=module_schemas[entity])
            for entity in sorted(scoped_entities)
            if entity in module_schemas
        ]
        if not contexts:
            return []

        lookup_nodes: dict[str, LookupPlanNode] = {}
        self._plan_recursive(
            contexts,
            segmented,
            prefix=(),
            array_ancestors=(),
            lookup_nodes=lookup_nodes,
            actor_level=actor_level,
            value_paths=value_paths or set(),
        )
        return [lookup_nodes[k] for k in sorted(lookup_nodes.keys())]

    def _plan_recursive(
        self,
        contexts: list[ResolveContext],
        paths: list[list[str]],
        *,
        prefix: tuple[str, ...],
        array_ancestors: tuple[str, ...],
        lookup_nodes: dict[str, LookupPlanNode],
        actor_level: int,
        value_paths: set[str],
    ) -> None:
        if not contexts or not paths:
            return

        by_head: dict[str, list[list[str]]] = {}
        for path in paths:
            if not path:
                continue
            by_head.setdefault(path[0], []).append(path[1:])

        for seg, remainders in by_head.items():
            has_descent = any(rem for rem in remainders)
            resolution = self._schema_resolver.resolve_segment(
                contexts,
                segment=seg,
                prefix=prefix,
                actor_level=actor_level,
                has_descent=has_descent,
                inspect_contents=".".join((*prefix, seg)) in value_paths,
            )
            if resolution.behavior.is_array_container or resolution.behavior.is_multi_reference:
                if any(rem and rem[0].isdecimal() for rem in remainders):
                    raise QueryValidationError(f"Array indices are not supported at path '{'.'.join(resolution.path)}'")

            if resolution.behavior.is_reference:
                if any(rem and rem[0] == "_id" for rem in remainders):
                    raise QueryValidationError(
                        f"MongoDB '_id' is not available through reference '{'.'.join(resolution.path)}'; use 'id'"
                    )
                if has_descent:
                    if resolution.target is None:
                        continue

                    link_module = resolution.target.module
                    linked_entities = set(resolution.target.entities)
                    if not isinstance(link_module, str) or not link_module:
                        raise QueryValidationError(f"Link module collision at path '{'.'.join((*prefix, seg))}'")
                    if not linked_entities and resolution.target.entity_scope_mode == "all_module":
                        linked_entities = {
                            ctx.entity
                            for ctx in resolution.next_contexts
                            if ctx.module == link_module and isinstance(ctx.entity, str)
                        }

                    full_path = ".".join((*prefix, seg))
                    node = lookup_nodes.get(full_path)
                    if node is None:
                        node = LookupPlanNode(
                            path=full_path,
                            is_multi_link=resolution.behavior.is_multi_reference,
                            link_module=link_module,
                            link_entities=tuple(sorted(linked_entities)),
                            entities_by_source=resolution.target.entities_by_source,
                            array_ancestors=array_ancestors,
                        )
                        lookup_nodes[full_path] = node

                    child_paths = [rem for rem in remainders if rem and rem[0] != "*"]
                    if child_paths and resolution.next_contexts:
                        self._plan_recursive(
                            resolution.next_contexts,
                            child_paths,
                            prefix=(*prefix, seg),
                            array_ancestors=(),
                            lookup_nodes=node.children,
                            actor_level=actor_level,
                            value_paths=value_paths,
                        )
                continue

            child_paths = [rem for rem in remainders if rem and rem[0] != "*"]
            if not child_paths:
                continue

            if not resolution.next_contexts:
                raise QueryValidationError(f"Cannot traverse through non-container field '{'.'.join((*prefix, seg))}'")

            child_array_ancestors = array_ancestors
            if resolution.behavior.is_array_container:
                child_array_ancestors = (*array_ancestors, ".".join(resolution.path))

            self._plan_recursive(
                resolution.next_contexts,
                child_paths,
                prefix=(*prefix, seg),
                array_ancestors=child_array_ancestors,
                lookup_nodes=lookup_nodes,
                actor_level=actor_level,
                value_paths=value_paths,
            )
