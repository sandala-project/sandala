from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ReferenceTarget:
    entity_scope_mode: str = "explicit"
    module: str | None = None
    entities: tuple[str, ...] = ()
    # Needed only when explicit target scopes differ between source entities.
    entities_by_source: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class FieldBehavior:
    semantic_type: str
    is_container: bool
    is_array_container: bool
    is_reference: bool
    is_multi_reference: bool


class SemanticStrategy(Protocol):
    def behavior(self, field_schema: dict[str, Any]) -> FieldBehavior: ...

    def child_schema(self, field_schema: dict[str, Any]) -> dict[str, Any] | None: ...

    def reference_target(
        self,
        *,
        module: str,
        entity: str,
        field_path: tuple[str, ...],
        field_schema: dict[str, Any],
    ) -> ReferenceTarget | None: ...


class ScalarStrategy:
    def behavior(self, field_schema: dict[str, Any]) -> FieldBehavior:
        return FieldBehavior(
            semantic_type="Scalar",
            is_container=False,
            is_array_container=False,
            is_reference=False,
            is_multi_reference=False,
        )

    def child_schema(self, field_schema: dict[str, Any]) -> dict[str, Any] | None:
        return None

    def reference_target(
        self,
        *,
        module: str,
        entity: str,
        field_path: tuple[str, ...],
        field_schema: dict[str, Any],
    ) -> ReferenceTarget | None:
        return None


class ObjectLikeStrategy:
    def __init__(self, semantic_type: str):
        self._semantic_type = semantic_type

    def behavior(self, field_schema: dict[str, Any]) -> FieldBehavior:
        return FieldBehavior(
            semantic_type=self._semantic_type,
            is_container=True,
            is_array_container=False,
            is_reference=False,
            is_multi_reference=False,
        )

    def child_schema(self, field_schema: dict[str, Any]) -> dict[str, Any] | None:
        return field_schema

    def reference_target(
        self,
        *,
        module: str,
        entity: str,
        field_path: tuple[str, ...],
        field_schema: dict[str, Any],
    ) -> ReferenceTarget | None:
        return None


class ArrayStrategy:
    def behavior(self, field_schema: dict[str, Any]) -> FieldBehavior:
        return FieldBehavior(
            semantic_type="Array",
            is_container=True,
            is_array_container=True,
            is_reference=False,
            is_multi_reference=False,
        )

    def child_schema(self, field_schema: dict[str, Any]) -> dict[str, Any] | None:
        items = field_schema.get("items")
        return items if isinstance(items, dict) else None

    def reference_target(
        self,
        *,
        module: str,
        entity: str,
        field_path: tuple[str, ...],
        field_schema: dict[str, Any],
    ) -> ReferenceTarget | None:
        return None


class LinkStrategy:
    def __init__(self, semantic_type: str, *, is_multi: bool):
        self._semantic_type = semantic_type
        self._is_multi = is_multi

    def behavior(self, field_schema: dict[str, Any]) -> FieldBehavior:
        return FieldBehavior(
            semantic_type=self._semantic_type,
            is_container=False,
            is_array_container=False,
            is_reference=True,
            is_multi_reference=self._is_multi,
        )

    def child_schema(self, field_schema: dict[str, Any]) -> dict[str, Any] | None:
        return None

    def reference_target(
        self,
        *,
        module: str,
        entity: str,
        field_path: tuple[str, ...],
        field_schema: dict[str, Any],
    ) -> ReferenceTarget | None:
        meta = field_schema.get("x-meta", {})
        link = meta.get("link", {})
        link_module = link.get("module")
        if not isinstance(link_module, str) or not link_module:
            return None
        entities = link.get("entities", [])
        if not isinstance(entities, list):
            entities = []
        return ReferenceTarget(
            entity_scope_mode="explicit",
            module=link_module,
            entities=tuple(sorted({item for item in entities if isinstance(item, str)})),
        )


class NodeRelationStrategy:
    def __init__(self, semantic_type: str, *, is_multi: bool):
        self._semantic_type = semantic_type
        self._is_multi = is_multi

    def behavior(self, field_schema: dict[str, Any]) -> FieldBehavior:
        return FieldBehavior(
            semantic_type=self._semantic_type,
            is_container=False,
            is_array_container=False,
            is_reference=True,
            is_multi_reference=self._is_multi,
        )

    def child_schema(self, field_schema: dict[str, Any]) -> dict[str, Any] | None:
        return None

    def reference_target(
        self,
        *,
        module: str,
        entity: str,
        field_path: tuple[str, ...],
        field_schema: dict[str, Any],
    ) -> ReferenceTarget | None:
        return ReferenceTarget(
            entity_scope_mode="all_module",
            module=module,
        )


class SemanticRegistry:
    def __init__(self, strategies: dict[str, SemanticStrategy], default_strategy: SemanticStrategy):
        self._strategies = strategies
        self._default = default_strategy

    def strategy_for(self, field_schema: dict[str, Any]) -> SemanticStrategy:
        semantic = field_schema.get("x-meta", {}).get("semantic-type")
        if isinstance(semantic, str) and semantic in self._strategies:
            return self._strategies[semantic]
        field_type = field_schema.get("type")
        if field_type == "object" and "Object" in self._strategies:
            return self._strategies["Object"]
        if field_type == "array" and "Array" in self._strategies:
            return self._strategies["Array"]
        return self._default

    def behavior_for(self, field_schema: dict[str, Any]) -> FieldBehavior:
        return self.strategy_for(field_schema).behavior(field_schema)


def default_semantic_registry() -> SemanticRegistry:
    default = ScalarStrategy()
    strategies: dict[str, SemanticStrategy] = {
        "Object": ObjectLikeStrategy("Object"),
        "Array": ArrayStrategy(),
        "File": ObjectLikeStrategy("File"),
        "Image": ObjectLikeStrategy("Image"),
        "Video": ObjectLikeStrategy("Video"),
        "Link": LinkStrategy("Link", is_multi=False),
        "LinkArray": LinkStrategy("LinkArray", is_multi=True),
        "NodeParentRef": NodeRelationStrategy("NodeParentRef", is_multi=False),
        "NodeAncestorsRef": NodeRelationStrategy("NodeAncestorsRef", is_multi=True),
    }
    return SemanticRegistry(strategies=strategies, default_strategy=default)
