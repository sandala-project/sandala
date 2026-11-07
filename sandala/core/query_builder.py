from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import cache
from typing import Any

from sandala.core.access import ACTOR_ROLE_ORDER, normalize_actor_role
from sandala.core.errors import QueryValidationError
from sandala.core.query.acl_filter import build_node_permission_filter
from sandala.core.query.filter_compiler import FilterCompiler
from sandala.core.query.lookup_pipeline_builder import LookupBuildContext, LookupPipelineBuilder
from sandala.core.query.lookup_planner import LookupPlanNode, LookupPlanner
from sandala.core.query.path_utils import relative_under_prefix, split_field_path
from sandala.core.query.pipeline_builder import MongoPipelineBuilder, PipelineBuildInput
from sandala.core.query.projection_normalizer import ProjectionNormalizer
from sandala.core.query.reference_resolution_conflicts import validate_terminal_reference_paths
from sandala.core.query.schema_resolver import SchemaPathResolver
from sandala.core.query.semantic_registry import default_semantic_registry
from sandala.core.query.system_fields import SystemFieldProvider
from sandala.core.query.visibility_exclusions import VisibilityExclusionsCollector
from sandala.core.services.node_hooks import NodeHookRegistry, NodeQueryHookContext


_ACL_RAW_OWNER_FIELD = "__sandala_acl_raw_owner"
_ACL_RAW_GROUP_FIELD = "__sandala_acl_raw_group"
_MAX_PAGINATION_VALUE = 2**63 - 1


@dataclass(frozen=True)
class BuiltQuery:
    pipeline: list[dict[str, Any]]
    query: dict[str, Any]


class _QuerySchemaContext:
    """Schema-dependent components and lazy schema reads for one build only."""

    def __init__(self, entity_repo, semantic_registry, system_fields):
        self.get_module_schemas = cache(entity_repo.get_module_schemas)
        self.filter_compiler = FilterCompiler(self.get_module_schemas, semantic_registry, system_fields)
        self.resolver = SchemaPathResolver(self.get_module_schemas, semantic_registry, system_fields)
        self.lookup_planner = LookupPlanner(self.get_module_schemas, self.resolver)
        self.visibility_exclusions = VisibilityExclusionsCollector(self.get_module_schemas, semantic_registry)


class QueryBuilder:
    def __init__(self, entity_repo, *, semantic_registry=None, system_fields=None, hook_registry: NodeHookRegistry | None = None):
        self._entity_repo = entity_repo
        self._hooks = hook_registry or NodeHookRegistry()
        self._semantic_registry = semantic_registry or default_semantic_registry()
        self._system_fields = system_fields or SystemFieldProvider()
        self._pipeline_builder = MongoPipelineBuilder()
        self._projection_normalizer = ProjectionNormalizer()
        self._lookup_pipeline_builder = LookupPipelineBuilder()

    def build(self, module: str, payload: dict[str, Any] | None, *, actor: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self.build_query(module, payload, actor=actor).pipeline

    def build_query(self, module: str, payload: dict[str, Any] | None, *, actor: dict[str, Any] | None = None) -> BuiltQuery:
        body = deepcopy(payload) if payload is not None else {}
        if not isinstance(body, dict):
            raise QueryValidationError("Query payload must be an object")

        schemas = _QuerySchemaContext(self._entity_repo, self._semantic_registry, self._system_fields)
        filter_compiler = schemas.filter_compiler
        actor_level = self._actor_access_level(actor)
        module_schemas = schemas.get_module_schemas(module)
        hook_context = NodeQueryHookContext(
            event="before_query",
            module=module,
            actor=deepcopy(actor),
            query=body,
        )
        self._hooks.dispatch(hook_context)
        body = hook_context.query
        if not isinstance(body, dict):
            raise QueryValidationError("Query payload must be an object")

        project = self._normalize_project(body.get("project", "*"))
        filter_dsl = body.get("filter", {})
        sort_dsl = self._normalize_sort(body.get("sort", {}))
        limit = body.get("limit")
        offset = body.get("offset", 0)

        if not isinstance(filter_dsl, dict):
            raise QueryValidationError("filter must be an object")
        if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0):
            raise QueryValidationError("limit must be positive integer")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise QueryValidationError("offset must be non-negative integer")
        if limit is not None and limit > _MAX_PAGINATION_VALUE:
            raise QueryValidationError(f"limit must not exceed {_MAX_PAGINATION_VALUE}")
        if offset > _MAX_PAGINATION_VALUE:
            raise QueryValidationError(f"offset must not exceed {_MAX_PAGINATION_VALUE}")
        permission_filter = build_node_permission_filter(actor, "r")
        system_filter = self._build_system_filter(permission_filter)
        filter_compiler.validate_deleted_filter_restrictions(filter_dsl)
        if permission_filter is not None:
            filter_compiler.validate_acl_filter_restrictions(filter_dsl)

        scoped_entities = self._infer_scoped_entities(filter_dsl, module_schemas)
        required_filter = self._compile_required_filters(module, frozenset(scoped_entities), hook_context.required_filters, schemas)
        hook_exclusions = set(hook_context.excluded_fields)

        lookup_paths_input = self._collect_lookup_input_paths(project, filter_dsl, sort_dsl, filter_compiler)
        lookup_tree = schemas.lookup_planner.plan(
            module,
            scoped_entities,
            lookup_paths_input,
            actor_level=actor_level,
            value_paths=filter_compiler.collect_filter_paths(filter_dsl, value_only=True) | set(sort_dsl),
        )
        raw_acl_fields = self._raw_acl_fields_for_final_match(lookup_tree, permission_filter)
        final_permission_filter = build_node_permission_filter(
            actor,
            "r",
            owner_field=_ACL_RAW_OWNER_FIELD if "owner" in raw_acl_fields else "owner",
            group_field=_ACL_RAW_GROUP_FIELD if "group" in raw_acl_fields else "group",
        )
        final_system_filter = self._build_system_filter(final_permission_filter)
        validate_terminal_reference_paths(
            lookup_tree,
            filter_dsl=filter_dsl,
            sort_paths=set(sort_dsl),
        )
        project_paths = [p for p in project if p != "*"]
        final_projection_paths = self._projection_normalizer.normalize_final(project_paths)
        lookup_projection_paths = self._projection_normalizer.normalize_lookup(project_paths)
        aux_paths = sorted(filter_compiler.collect_filter_paths(filter_dsl) | set(sort_dsl.keys()))

        initial_match = filter_compiler.build_initial_match(
            module,
            filter_dsl,
            scoped_entities,
            system_filter=system_filter,
        )
        if required_filter:
            initial_match = filter_compiler.combine_with_system_filter(required_filter, initial_match)
        compiled_filter = filter_compiler.compile_filter(filter_dsl)
        final_match = filter_compiler.combine_with_system_filter(compiled_filter, final_system_filter)
        if required_filter and not lookup_tree:
            final_match = filter_compiler.combine_with_system_filter(required_filter, final_match)
        sort_stage = self._pipeline_builder.compile_sort(sort_dsl)
        project_stage = self._pipeline_builder.build_projection(project, final_projection_paths)
        field_exclusions = self._projection_normalizer.filter_exclusions(
            schemas.visibility_exclusions.collect(module, scoped_entities, actor_level=actor_level),
            project_stage,
        )

        lookup_stages = self._build_lookup_stages(
            lookup_tree,
            current_prefix="",
            lookup_projection_paths=lookup_projection_paths,
            aux_paths=aux_paths,
            actor_level=actor_level,
            system_filter=system_filter,
            actor=actor,
            hook_exclusions=hook_exclusions,
            schemas=schemas,
        )
        if raw_acl_fields:
            lookup_stages.insert(
                0,
                {
                    "$set": {
                        raw_field: f"${field}"
                        for field, raw_field in raw_acl_fields.items()
                    }
                },
            )

        if hook_exclusions:
            field_exclusions = self._projection_normalizer.normalize_exclusions(
                {*field_exclusions, *hook_exclusions}
            )

        pipeline = self._pipeline_builder.build_pipeline(
            PipelineBuildInput(
                initial_match=initial_match,
                final_match=final_match,
                lookup_stages=lookup_stages,
                sort_stage=sort_stage,
                project_stage=project_stage,
                field_exclusions=field_exclusions,
                post_match_unset=sorted(raw_acl_fields.values()),
                offset=offset,
                limit=limit,
            )
        )
        return BuiltQuery(pipeline=pipeline, query=body)

    def _raw_acl_fields_for_final_match(
        self,
        lookup_tree: list[LookupPlanNode],
        permission_filter: dict[str, Any] | None,
    ) -> dict[str, str]:
        if permission_filter is None:
            return {}
        paths = {node.path for node in lookup_tree}
        result: dict[str, str] = {}
        if "owner" in paths:
            result["owner"] = _ACL_RAW_OWNER_FIELD
        if "group" in paths:
            result["group"] = _ACL_RAW_GROUP_FIELD
        return result

    def _normalize_project(self, project: Any) -> list[str]:
        if project == "*":
            return ["*"]
        if not isinstance(project, list) or not project:
            raise QueryValidationError("project must be '*' or non-empty array")
        for item in project:
            if not isinstance(item, str) or not item:
                raise QueryValidationError("project must contain non-empty strings")
            if item == "_id" or item.startswith("_id."):
                raise QueryValidationError("MongoDB '_id' cannot be projected; use the public 'id' field")
        return project

    def _normalize_sort(self, sort: Any) -> dict[str, Any]:
        if not isinstance(sort, dict):
            raise QueryValidationError("sort must be an object")

        normalized = dict(sort)
        normalized.setdefault("_id", "asc")
        return normalized

    def _collect_lookup_input_paths(
        self, project: list[str], filter_dsl: dict[str, Any], sort_dsl: dict[str, Any], filter_compiler: FilterCompiler,
    ) -> list[str]:
        paths: set[str] = set()
        for item in project:
            if item != "*":
                paths.add(item)
        paths.update(filter_compiler.collect_filter_paths(filter_dsl))
        for key in sort_dsl.keys():
            split_field_path(key)
            paths.add(key)
        return sorted(paths)

    def _infer_scoped_entities(self, filter_dsl: dict[str, Any], module_schemas: dict[str, dict[str, Any]]) -> set[str]:
        all_entities = set(module_schemas.keys())
        if not all_entities:
            return set()

        entity_predicate = filter_dsl.get("entity") if isinstance(filter_dsl, dict) else None
        if entity_predicate is None:
            return all_entities
        if isinstance(entity_predicate, str):
            return {entity_predicate} & all_entities
        if not isinstance(entity_predicate, dict):
            return all_entities

        if "eq" in entity_predicate and isinstance(entity_predicate["eq"], str):
            return {entity_predicate["eq"]} & all_entities
        if "in" in entity_predicate and isinstance(entity_predicate["in"], list):
            return {item for item in entity_predicate["in"] if isinstance(item, str)} & all_entities
        return all_entities

    def _build_lookup_stages(
        self,
        lookup_nodes: list[LookupPlanNode],
        *,
        current_prefix: str,
        lookup_projection_paths: list[str],
        aux_paths: list[str],
        actor_level: int,
        system_filter: dict[str, Any],
        actor: dict[str, Any] | None,
        hook_exclusions: set[str],
        schemas: _QuerySchemaContext,
    ) -> list[dict[str, Any]]:
        context = LookupBuildContext(
            system_filter=system_filter,
            collect_visibility_exclusions=lambda node, projection: self._projection_normalizer.filter_exclusions(
                schemas.visibility_exclusions.collect(node.link_module, set(node.link_entities), actor_level=actor_level),
                projection,
            ),
            build_lookup_projection=lambda node_path, child_nodes: self._build_lookup_projection(
                node_path,
                child_nodes,
                lookup_projection_paths,
                aux_paths,
            ),
            build_required_filter=lambda node: self._build_lookup_hook_filter(node, actor, hook_exclusions, schemas),
        )
        return self._lookup_pipeline_builder.build_lookup_stages(
            lookup_nodes,
            current_prefix=current_prefix,
            context=context,
        )

    def _build_lookup_hook_filter(
        self,
        node: LookupPlanNode,
        actor: dict[str, Any] | None,
        hook_exclusions: set[str],
        schemas: _QuerySchemaContext,
    ) -> dict[str, Any]:
        if not self._hooks.has_hooks("before_query", module=node.link_module):
            return {}
        context = NodeQueryHookContext(
            event="before_query",
            module=node.link_module,
            actor=deepcopy(actor),
            path=node.path,
        )
        self._hooks.dispatch(context)
        hook_exclusions.update(f"{node.path}.{path}" for path in context.excluded_fields)
        return self._compile_required_filters(
            node.link_module, frozenset(node.link_entities), context.required_filters, schemas
        )

    def _compile_required_filters(
        self,
        module: str,
        entities: frozenset[str],
        filters: tuple[dict[str, Any], ...],
        schemas: _QuerySchemaContext,
    ) -> dict[str, Any]:
        filters = tuple(predicate for predicate in filters if predicate)
        if not filters:
            return {}
        filter_dsl = filters[0] if len(filters) == 1 else {"and": list(filters)}
        paths = schemas.filter_compiler.collect_filter_paths(filter_dsl)
        schemas.resolver.validate_stored_paths(module, entities, paths)
        return schemas.filter_compiler.compile_filter(filter_dsl)

    def _build_lookup_projection(
        self,
        node_path: str,
        child_nodes: list[LookupPlanNode],
        lookup_projection_paths: list[str],
        aux_paths: list[str],
    ) -> dict[str, int]:
        if node_path in lookup_projection_paths:
            return {"_id": 0}

        include_fields: set[str] = set()
        for path in [*lookup_projection_paths, *aux_paths]:
            rel = relative_under_prefix(path, node_path)
            if not rel:
                continue
            include_fields.add(rel.split(".", 1)[0])

        for child in child_nodes:
            child_rel = relative_under_prefix(child.path, node_path)
            if child_rel:
                include_fields.add(child_rel.split(".", 1)[0])

        project = {"_id": 0}
        for field in sorted(include_fields):
            project[field] = 1
        return project

    def _actor_access_level(self, actor: dict[str, Any] | None) -> int:
        return ACTOR_ROLE_ORDER[normalize_actor_role(actor)]

    def _build_system_filter(self, permission_filter: dict[str, Any] | None) -> dict[str, Any]:
        predicates = [{"deleted": {"$eq": False}}]
        if permission_filter is not None:
            predicates.append(permission_filter)
        if len(predicates) == 1:
            return predicates[0]
        return {
            "$and": predicates
        }
