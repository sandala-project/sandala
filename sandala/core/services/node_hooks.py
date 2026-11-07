from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from sandala.core.errors import QueryValidationError


QUERY_HOOK_EVENTS = {"before_query", "after_query"}

NODE_HOOK_EVENTS = {
    "before_create",
    "after_create",
    "before_patch",
    "after_patch",
    "before_acl_patch",
    "after_acl_patch",
    "before_delete",
    "after_delete",
    *QUERY_HOOK_EVENTS,
}


@dataclass(slots=True)
class NodeHookContext:
    event: str
    module: str
    entity: str
    node_id: str | None = None
    actor: dict[str, Any] | None = None
    effective_actor: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    current: dict[str, Any] | None = None
    candidate: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    deleted_count: int | None = None


@dataclass(slots=True)
class NodeQueryHookContext:
    event: str
    module: str
    actor: dict[str, Any] | None = None
    query: dict[str, Any] | None = None
    path: str = ""
    result: list[dict[str, Any]] | None = None
    _required_filters: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _excluded_fields: set[str] = field(default_factory=set, init=False, repr=False)

    @property
    def is_lookup(self) -> bool:
        return bool(self.path)

    @property
    def required_filters(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(self._required_filters))

    @property
    def excluded_fields(self) -> tuple[str, ...]:
        return tuple(sorted(self._excluded_fields))

    def add_required_filter(self, filter_dsl: dict[str, Any]) -> None:
        self._ensure_before_query()
        if not isinstance(filter_dsl, dict):
            raise QueryValidationError("Required filter must be an object")
        self._required_filters.append(deepcopy(filter_dsl))

    def exclude_fields(self, *paths: str) -> None:
        self._ensure_before_query()
        for path in paths:
            if not isinstance(path, str) or any(
                not segment or segment.startswith("$") or "*" in segment or "\x00" in segment
                for segment in path.split(".")
            ):
                raise QueryValidationError("Excluded fields must be non-empty field paths without wildcards")
        self._excluded_fields.update(paths)

    def _ensure_before_query(self) -> None:
        if self.event != "before_query":
            raise ValueError("Query restrictions can only be added in before_query")


NodeHook = Callable[[NodeHookContext | NodeQueryHookContext], None]


@dataclass(slots=True)
class _RegisteredHook:
    order: int
    priority: int
    module: str | None
    entity: str | None
    handler: NodeHook


class NodeHookRegistry:
    def __init__(self) -> None:
        self._hooks: dict[str, list[_RegisteredHook]] = {event: [] for event in NODE_HOOK_EVENTS}
        self._next_order = 0

    def register(
        self,
        event: str,
        handler: NodeHook,
        *,
        module: str | None = None,
        entity: str | None = None,
        priority: int = 100,
    ) -> NodeHook:
        if event not in NODE_HOOK_EVENTS:
            raise ValueError(f"Unsupported node hook event '{event}'")
        if event in QUERY_HOOK_EVENTS and entity is not None:
            raise ValueError("Query hooks can only be scoped by module, not entity")
        if not callable(handler):
            raise TypeError("Node hook handler must be callable")

        self._hooks[event].append(
            _RegisteredHook(
                order=self._next_order,
                priority=priority,
                module=module,
                entity=entity,
                handler=handler,
            )
        )
        self._next_order += 1
        return handler

    def dispatch(self, context: NodeHookContext | NodeQueryHookContext) -> None:
        if context.event not in NODE_HOOK_EVENTS:
            raise ValueError(f"Unsupported node hook event '{context.event}'")

        hooks = sorted(self._hooks[context.event], key=lambda item: (item.priority, item.order))
        for hook in hooks:
            if hook.module is not None and hook.module != context.module:
                continue
            if hook.entity is not None and (
                not isinstance(context, NodeHookContext) or hook.entity != context.entity
            ):
                continue
            hook.handler(context)

    def has_hooks(self, event: str, *, module: str | None = None, entity: str | None = None) -> bool:
        if event not in NODE_HOOK_EVENTS:
            raise ValueError(f"Unsupported node hook event '{event}'")
        for hook in self._hooks[event]:
            if module is not None and hook.module is not None and hook.module != module:
                continue
            if entity is not None and hook.entity is not None and hook.entity != entity:
                continue
            return True
        return False
