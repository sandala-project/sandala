from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sandala.core.errors import ValidationError


@dataclass(frozen=True)
class LookupBuildContext:
    system_filter: dict[str, Any]
    collect_visibility_exclusions: Callable[[Any, dict[str, int]], list[str]]
    build_lookup_projection: Callable[[str, list[Any]], dict[str, int]]
    build_required_filter: Callable[[Any], dict[str, Any]] | None = None


class LookupPipelineBuilder:
    def build_lookup_stages(
        self,
        lookup_nodes: list[Any],
        *,
        current_prefix: str,
        context: LookupBuildContext,
    ) -> list[dict[str, Any]]:
        stages: list[dict[str, Any]] = []
        for node in lookup_nodes:
            relative_arrays = [self._relative_path(path, current_prefix) for path in node.array_ancestors]
            if relative_arrays:
                stages.extend(
                    self._build_array_lookup_stages(
                        node,
                        current_prefix=current_prefix,
                        relative_array_paths=relative_arrays,
                        context=context,
                    )
                )
                continue

            stages.extend(
                self._build_regular_lookup_stages(
                    node,
                    current_prefix=current_prefix,
                    context=context,
                )
            )

        return stages

    def _build_regular_lookup_stages(
        self,
        node: Any,
        *,
        current_prefix: str,
        context: LookupBuildContext,
    ) -> list[dict[str, Any]]:
        relative_path = self._relative_path(node.path, current_prefix)
        linked_entities = list(node.link_entities)
        child_nodes = [node.children[k] for k in sorted(node.children.keys())]
        required_filter = context.build_required_filter(node) if context.build_required_filter is not None else {}

        nested_pipeline = self._build_lookup_nested_pipeline(
            node,
            child_nodes,
            context=context,
        )

        lookup_as = self._temp_field_name("lookup", node.path, current_prefix)
        local_field = relative_path
        entity_match = {"entity": {"$in": linked_entities}}
        lookup_match = {"$and": [context.system_filter, entity_match]}
        if required_filter:
            lookup_match["$and"].append(required_filter)
        lookup = {
            "$lookup": {
                "from": node.link_module,
                "localField": local_field,
                "foreignField": "id",
                "pipeline": [
                    {"$match": lookup_match},
                    *nested_pipeline,
                ],
                "as": lookup_as,
            }
        }
        if node.entities_by_source:
            lookup["$lookup"]["let"] = {"source_entity": "$entity"}
            lookup_match["$and"].append({"$expr": self._build_source_entity_filter(node.entities_by_source)})
        value: Any = f"${lookup_as}" if node.is_multi_link else {"$ifNull": [{"$first": f"${lookup_as}"}, None]}
        # A lookup always returns an array, even for a missing/null local field.
        # Preserve those source states; only existing reference values resolve.
        value = {"$cond": [
            {"$in": [{"$type": f"${relative_path}"}, ["missing", "null"]]},
            f"${relative_path}",
            value,
        ]}
        root_path = (
            self._relative_path(node.array_ancestors[-1], current_prefix)
            if node.array_ancestors else relative_path.split(".")[0]
        )
        # Arrays have already been unwound. Rebuild only the affected object
        # branch (or array element), retaining absent/null parents and siblings.
        parts = relative_path.split(".")
        for i in reversed(range(len(root_path.split(".")), len(parts))):
            parent_path = ".".join(parts[:i])
            value = {"$cond": [
                {"$eq": [{"$type": f"${parent_path}"}, "object"]},
                {"$mergeObjects": [f"${parent_path}", {parts[i]: value}]},
                f"${parent_path}",
            ]}
        return [lookup, {"$set": {root_path: value, lookup_as: "$$REMOVE"}}]

    def _build_source_entity_filter(self, entities_by_source: tuple[tuple[str, tuple[str, ...]], ...]) -> dict[str, Any]:
        groups: dict[tuple[str, ...], list[str]] = {}
        for source, entities in entities_by_source:
            if entities:
                groups.setdefault(entities, []).append(source)
        clauses = [
            {"$and": [
                {"$in": ["$$source_entity", {"$literal": sources}]},
                {"$in": ["$entity", {"$literal": list(entities)}]},
            ]}
            for entities, sources in sorted(groups.items())
        ]
        return clauses[0] if len(clauses) == 1 else {"$or": clauses}

    def _build_lookup_nested_pipeline(
        self,
        node: Any,
        child_nodes: list[Any],
        *,
        context: LookupBuildContext,
    ) -> list[dict[str, Any]]:
        nested_pipeline: list[dict[str, Any]] = []
        projection = context.build_lookup_projection(node.path, child_nodes)
        visibility_exclusions = context.collect_visibility_exclusions(node, projection)
        nested_pipeline.extend(
            self.build_lookup_stages(
                child_nodes,
                current_prefix=node.path,
                context=context,
            )
        )
        nested_pipeline.append({"$project": projection})
        if visibility_exclusions:
            nested_pipeline.append({"$unset": visibility_exclusions})
        return nested_pipeline

    def _build_array_lookup_stages(
        self,
        node: Any,
        *,
        current_prefix: str,
        relative_array_paths: list[str],
        context: LookupBuildContext,
    ) -> list[dict[str, Any]]:
        base_field = self._temp_field_name("base", node.path, current_prefix)
        pairs_field = self._temp_field_name("pairs", node.path, current_prefix)
        index_fields = [
            self._temp_field_name(f"idx_{i}", node.path, current_prefix)
            for i in range(len(relative_array_paths))
        ]
        state_fields = [
            self._temp_field_name(f"array_{i}", node.path, current_prefix)
            for i in range(len(relative_array_paths))
        ]
        cleanup = [*index_fields, *state_fields]
        parent_states: list[list[tuple[str, str]]] = []
        stages: list[dict[str, Any]] = []
        previous_path = ""

        # Each array path needs its own index. Capture null/missing parents
        # before dotted writes while traversing the intervening objects.
        for i, array_path in enumerate(relative_array_paths):
            parents = self._parent_states(previous_path, array_path, state_fields[i])
            parent_states.append(parents)
            cleanup.extend(state for _, state in parents)
            stages.append({"$set": {
                state_fields[i]: self._value_state(array_path, "array"),
                **{state: self._value_state(path, "object") for path, state in parents},
            }})
            stages.append({"$unwind": {
                "path": f"${array_path}",
                "includeArrayIndex": index_fields[i],
                "preserveNullAndEmptyArrays": True,
            }})
            previous_path = array_path

        stages.extend(
            self._build_regular_lookup_stages(
                node,
                current_prefix=current_prefix,
                context=context,
            )
        )

        for i in reversed(range(len(relative_array_paths))):
            array_path = relative_array_paths[i]
            state = state_fields[i]
            # Each outer index is part of the key: inner arrays belonging to
            # different outer elements must never be reconstructed together.
            group_key: Any = {
                "node": "$_id",
                **{f"i{j}": f"${index}" for j, index in enumerate(index_fields[:i])},
            } if i else "$_id"
            restored_array = {"$cond": [
                {"$eq": [f"${base_field}.{state}.kind", "array"]},
                {"$map": {
                    "input": {"$filter": {
                        "input": f"${pairs_field}",
                        "as": "pair",
                        "cond": {"$ne": ["$$pair.i", None]},
                    }},
                    "as": "pair",
                    "in": "$$pair.v",
                }},
                {"$cond": [
                    {"$eq": [f"${base_field}.{state}.kind", "missing"]},
                    "$$REMOVE",
                    f"${base_field}.{state}.value",
                ]},
            ]}
            stages.extend([
                {"$sort": {"_id": 1, **{index: 1 for index in index_fields[:i + 1]}}},
                {"$group": {
                    "_id": group_key,
                    # Only one document snapshot per group, not a nested copy
                    # of the original document for every unwind level.
                    base_field: {"$first": "$$ROOT"},
                    pairs_field: {"$push": {"i": f"${index_fields[i]}", "v": f"${array_path}"}},
                }},
                {"$set": {f"{base_field}.{array_path}": restored_array}},
                {"$replaceRoot": {"newRoot": f"${base_field}"}},
            ])
            stages.extend(self._restore_parents(parent_states[i]))
        stages.append({"$unset": cleanup})
        return stages

    def _value_state(self, path: str, container_type: str) -> dict[str, Any]:
        # Containers are reconstructed, so copying their contents here would
        # only multiply memory usage while unwinding nested arrays.
        return {
            "kind": {"$type": f"${path}"},
            "value": {"$cond": [
                {"$eq": [{"$type": f"${path}"}, container_type]},
                None, {"$ifNull": [f"${path}", None]},
            ]},
        }

    def _parent_states(self, previous_path: str, path: str, state_prefix: str) -> list[tuple[str, str]]:
        parts = path.split(".")
        start = len(previous_path.split(".")) if previous_path else 1
        return [(".".join(parts[:i]), f"{state_prefix}_parent_{i}") for i in range(start, len(parts))]

    def _restore_parents(self, parents: list[tuple[str, str]]) -> list[dict[str, Any]]:
        stages = []
        # Separate stages avoid conflicting writes to a parent and its child.
        for path, state in reversed(parents):
            stages.append({"$set": {path: {"$cond": [
                {"$eq": [f"${state}.kind", "object"]},
                f"${path}",
                {"$cond": [
                    {"$eq": [f"${state}.kind", "missing"]}, "$$REMOVE", f"${state}.value",
                ]},
            ]}}})
        return stages

    def _temp_field_name(self, kind: str, node_path: str, current_prefix: str) -> str:
        rel = self._relative_path(node_path, current_prefix)
        suffix = rel.replace(".", "__")
        if not suffix:
            suffix = "root"
        return f"__sandala_{kind}_{suffix}"

    def _relative_path(self, full_path: str, current_prefix: str) -> str:
        if not current_prefix:
            return full_path
        prefix = f"{current_prefix}."
        if not full_path.startswith(prefix):
            raise ValidationError(f"Internal error: path '{full_path}' does not belong to prefix '{current_prefix}'")
        return full_path[len(prefix):]
