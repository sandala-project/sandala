from __future__ import annotations

from sandala.core.errors import QueryValidationError
from sandala.core.query.lookup_planner import LookupPlanNode


def validate_terminal_reference_paths(
    lookup_tree: list[LookupPlanNode],
    *,
    filter_dsl: dict[str, object],
    sort_paths: set[str],
) -> None:
    resolved_paths = _collect_lookup_paths(lookup_tree)
    filter_operations = _collect_terminal_filter_operations(filter_dsl)

    conflicting_filter_paths = sorted(resolved_paths.intersection(filter_operations))
    if conflicting_filter_paths:
        path = conflicting_filter_paths[0]
        operators = filter_operations[path]
        if operators == {"size"}:
            raise QueryValidationError(
                f"Filter path '{path}' uses size on a stored reference array but '{path}' is resolved by this query."
            )
        raise QueryValidationError(
            f"Filter path '{path}' compares a stored reference ID but '{path}' is resolved by this query. "
            f"Use '{path}.id' instead."
        )

    conflicting_sort_paths = sorted(resolved_paths.intersection(sort_paths))
    if conflicting_sort_paths:
        path = conflicting_sort_paths[0]
        raise QueryValidationError(
            f"Sort path '{path}' compares a stored reference ID but '{path}' is resolved by this query. "
            f"Use '{path}.id' instead."
        )


def _collect_lookup_paths(lookup_nodes: list[LookupPlanNode]) -> set[str]:
    paths: set[str] = set()
    for node in lookup_nodes:
        paths.add(node.path)
        paths.update(_collect_lookup_paths(list(node.children.values())))
    return paths


def _collect_terminal_filter_operations(filter_dsl: dict[str, object]) -> dict[str, set[str]]:
    operations: dict[str, set[str]] = {}
    for field, expression in filter_dsl.items():
        if field in {"and", "or", "not"}:
            if isinstance(expression, list):
                for item in expression:
                    if isinstance(item, dict):
                        for path, nested_operators in _collect_terminal_filter_operations(item).items():
                            operations.setdefault(path, set()).update(nested_operators)
            continue
        operations.setdefault(field, set()).update(_filter_operators(expression))
    return operations


def _filter_operators(expression: object) -> set[str]:
    if not isinstance(expression, dict):
        return {"eq"}
    return set(expression)
