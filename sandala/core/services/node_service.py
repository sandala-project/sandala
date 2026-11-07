from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from jsonschema import Draft7Validator, FormatChecker

from sandala.core.access import ACTOR_ROLE_ORDER, FIELD_ACCESS_MODE_ORDER, actor_has_role_at_least, normalize_actor_role
from sandala.core.errors import (
    AclFieldsNotAllowedInNodePatchError,
    AclPatchPayloadInvalidError,
    ConflictError,
    DescendantWriteForbiddenError,
    EntityNotAllowedInRootError,
    EntityNotAllowedUnderParentError,
    FieldWriteForbiddenError,
    GroupChangeForbiddenError,
    GroupNotFoundError,
    GroupNotInActorGroupsError,
    GroupRequiredError,
    LinkPatchAclHiddenReferencesMissingError,
    NodeIdAlreadyExistsError,
    NotFoundError,
    OwnerChangeForbiddenError,
    OwnerMustMatchActorError,
    OwnerNotFoundError,
    OwnerRequiredError,
    ParameterInvalidError,
    ParentCycleDetectedError,
    ParentNodeNotFoundError,
    ParentSameAsCurrentError,
    ParentWriteForbiddenError,
    PermChangeForbiddenError,
    QueryValidationError,
    RequestBodyInvalidError,
    RootCreateForbiddenError,
    ValidationError,
)
from sandala.core.query_builder import QueryBuilder
from sandala.core.query.acl_filter import build_node_permission_filter
from sandala.core.query.schema_utils import unwrap_nullable
from sandala.core.services.node_hooks import NodeHookContext, NodeHookRegistry, NodeQueryHookContext
from sandala.core.time_utils import utc_now_iso
from sandala.core.validation.error_normalizer import make_document_validation_error
from sandala.core.validation.schema_validator import build_effective_node_schema
from sandala.storage.errors import StorageQueryRejectedError

_USERS_MODULE = "users"
_USERS_USER_ENTITY = "user"
_USERS_GROUP_ENTITY = "group"
_ACL_FIELDS = frozenset({"owner", "group", "perm"})
_MISSING = object()


@dataclass(frozen=True)
class _LinkPatchPath:
    path: tuple[str | int, ...]
    target_entities: frozenset[str]
    target_module: str
    is_multi: bool


@dataclass(frozen=True)
class _ArrayNestedLinkPatchPath:
    array_path: tuple[str, ...]
    array_schema: dict[str, Any]
    relative_path: tuple[str | None, ...]
    target_entities: frozenset[str]
    target_module: str
    is_multi: bool


class NodeService:
    def __init__(self, entity_repo, node_repo, module_repo, hook_registry: NodeHookRegistry | None = None):
        self._entity_repo = entity_repo
        self._node_repo = node_repo
        self._module_repo = module_repo
        self.hooks = hook_registry or NodeHookRegistry()
        self._query_builder = QueryBuilder(entity_repo, hook_registry=self.hooks)

    def create(
        self,
        module: str,
        entity: str,
        payload: dict[str, Any],
        *,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RequestBodyInvalidError("Node payload must be an object")

        entity_schema = self._entity_repo.get_schema(module, entity)
        if entity_schema is None:
            raise NotFoundError(f"Entity '{entity}' in module '{module}' not found")

        self._enforce_write_mode(entity_schema, payload, actor=actor)

        hook_payload = deepcopy(payload)
        node_id = hook_payload.get("id")
        if node_id is None:
            node_id = str(uuid4())
            hook_payload["id"] = node_id

        hook_context = NodeHookContext(
            event="before_create",
            module=module,
            entity=entity,
            actor=deepcopy(actor),
            payload=hook_payload,
        )
        self.hooks.dispatch(
            hook_context
        )
        effective_actor = hook_context.actor

        now = utc_now_iso()
        candidate = deepcopy(hook_payload)
        self._validate_create_acl_input(candidate, actor=effective_actor)

        # Ignore and override system-managed fields.
        candidate["entity"] = entity
        candidate["deleted"] = False
        candidate["cdate"] = now
        candidate["mdate"] = now
        self._apply_acl_defaults(candidate, actor=effective_actor, entity_schema=entity_schema)
        self._validate_owner_group_references(
            owner_id=candidate.get("owner"),
            group_id=candidate.get("group"),
            actor=effective_actor,
        )

        node_id = candidate.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise ParameterInvalidError("Field 'id' must be a non-empty string when provided")

        parent: dict[str, Any] | None = None
        parent_id = candidate.get("parent")
        if parent_id is not None and not isinstance(parent_id, str):
            raise ParameterInvalidError("Field 'parent' must be string or null")
        if parent_id is not None:
            parent = self._node_repo.find_by_id(module, parent_id, deleted=False)
            if parent is None:
                raise ParentNodeNotFoundError(f"Parent node '{parent_id}' not found in module '{module}'")
            if not self._can_node_action(parent, actor=effective_actor, permission="p"):
                raise ParentWriteForbiddenError(f"Write to parent node '{parent_id}' is not allowed")
        else:
            self._enforce_root_create_permission(module, actor=effective_actor)
            self._enforce_root_entity_allowed(module, entity)

        depth, ancestors = self._build_hierarchy_fields(
            module,
            entity,
            parent_id,
            parent_node=parent,
        )
        candidate["parent"] = parent_id
        candidate["depth"] = depth
        candidate["ancestors"] = ancestors

        self._validate_node_candidate(candidate, entity_schema)
        _remove_transient_password_values(candidate, entity_schema)

        created = self._node_repo.insert_node(module, candidate)
        if created is None:
            if self._node_repo.find_by_id(module, node_id) is not None:
                raise NodeIdAlreadyExistsError(f"Node with id '{node_id}' already exists in module '{module}'")
            raise ConflictError("Node violates a unique index constraint")
        if self.hooks.has_hooks("after_create", module=module, entity=entity):
            self.hooks.dispatch(
                NodeHookContext(
                    event="after_create",
                    module=module,
                    entity=entity,
                    node_id=created.get("id"),
                    actor=deepcopy(actor),
                    effective_actor=deepcopy(effective_actor),
                    payload=deepcopy(hook_payload),
                    candidate=deepcopy(candidate),
                    result=deepcopy(created),
                )
            )
        return self._get_node_via_query(module, created["id"], entity=entity, actor=effective_actor)

    def query(
        self,
        module: str,
        payload: dict[str, Any] | None,
        *,
        actor: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        built_query = self._query_builder.build_query(module, payload, actor=actor)
        try:
            result = self._node_repo.aggregate(module, built_query.pipeline)
        except StorageQueryRejectedError as exc:
            raise QueryValidationError(str(exc)) from exc
        if self.hooks.has_hooks("after_query", module=module):
            context = NodeQueryHookContext(
                event="after_query",
                module=module,
                actor=deepcopy(actor),
                query=deepcopy(built_query.query),
                result=result,
            )
            self.hooks.dispatch(context)
            if not isinstance(context.result, list) or any(not isinstance(node, dict) for node in context.result):
                raise ValueError("after_query result must be a list of node objects")
            result = context.result
        return result

    def get(
        self,
        module: str,
        node_id: str,
        *,
        project: str | list[str] | None = None,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        node = self._get_node_for_read(module, node_id, actor=actor)
        entity = node.get("entity")
        if not isinstance(entity, str) or not entity:
            raise NotFoundError(f"Node '{node_id}' in module '{module}' not found")

        entity_schema = self._entity_repo.get_schema(module, entity)
        if entity_schema is None:
            raise NotFoundError(f"Entity '{entity}' in module '{module}' not found")

        effective_project = project if project is not None else self._build_default_read_project(entity_schema, actor=actor)
        nodes = self.query(
            module,
            {
                "filter": {"id": node_id, "entity": entity},
                "project": effective_project,
            },
            actor=actor,
        )
        if not nodes:
            raise NotFoundError(f"Node '{node_id}' in module '{module}' not found")
        return nodes[0]

    def list_entity(
        self,
        module: str,
        entity: str,
        payload: dict[str, Any] | None,
        *,
        actor: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        entity_schema = self._entity_repo.get_schema(module, entity)
        if entity_schema is None:
            raise NotFoundError(f"Entity '{entity}' in module '{module}' not found")

        if payload is not None and not isinstance(payload, dict):
            raise QueryValidationError("Query payload must be an object")

        effective_payload = deepcopy(payload or {})
        has_user_filter = "filter" in effective_payload
        user_filter = effective_payload.get("filter")
        effective_payload["filter"] = {"entity": entity}
        if has_user_filter:
            effective_payload["filter"]["and"] = [user_filter]
        if "project" not in effective_payload:
            effective_payload["project"] = self._build_default_read_project(entity_schema, actor=actor)

        return self.query(module, effective_payload, actor=actor)

    def patch(
        self,
        module: str,
        node_id: str,
        payload: dict[str, Any],
        *,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RequestBodyInvalidError("Node payload must be an object")

        current = self._node_repo.find_by_id(module, node_id, deleted=False)
        if current is None:
            raise NotFoundError(f"Node '{node_id}' in module '{module}' not found")
        entity = current.get("entity")
        if not isinstance(entity, str) or not entity:
            raise ValidationError(f"Node '{node_id}' in module '{module}' has invalid entity")

        entity_schema = self._entity_repo.get_schema(module, entity)
        if entity_schema is None:
            raise NotFoundError(f"Entity '{entity}' in module '{module}' not found")

        direct_acl_fields = sorted(
            key
            for key in _ACL_FIELDS
            if key in payload and payload[key] != current.get(key)
        )
        if direct_acl_fields:
            raise AclFieldsNotAllowedInNodePatchError(
                "ACL fields must be changed through PATCH /nodes/{module}/{id}/acl/",
            )

        self._enforce_write_mode(entity_schema, payload, actor=actor)

        if not self._can_node_action(current, actor=actor, permission="w"):
            raise ValidationError(f"Write to node '{node_id}' is not allowed")
        hook_payload = deepcopy(payload)
        self._protect_acl_hidden_references_in_patch(
            module,
            entity_schema,
            current=current,
            payload=hook_payload,
            actor=actor,
        )
        hook_context = NodeHookContext(
            event="before_patch",
            module=module,
            entity=entity,
            node_id=node_id,
            actor=deepcopy(actor),
            payload=hook_payload,
            current=deepcopy(current),
        )
        self.hooks.dispatch(
            hook_context
        )
        effective_actor = hook_context.actor

        self._validate_patch_acl_input(hook_payload, current=current, actor=effective_actor)
        if "owner" in hook_payload or "group" in hook_payload:
            self._validate_owner_group_references(
                owner_id=hook_payload.get("owner") if "owner" in hook_payload else None,
                group_id=hook_payload.get("group") if "group" in hook_payload else None,
                actor=effective_actor,
            )

        candidate = deepcopy(current)
        for key, value in hook_payload.items():
            if key in {"id", "entity", "ancestors", "depth", "deleted", "cdate", "mdate"}:
                continue
            candidate[key] = value

        if candidate.get("parent") is not None and not isinstance(candidate.get("parent"), str):
            raise ParameterInvalidError("Field 'parent' must be string or null")

        old_parent = current.get("parent")
        new_parent = candidate.get("parent")
        parent_changed = new_parent != old_parent

        if parent_changed:
            if new_parent == node_id:
                raise ParentSameAsCurrentError("Parent node cannot be the same as current node")

            if new_parent is not None:
                new_parent_node = self._node_repo.find_by_id(module, new_parent, deleted=False)
                if new_parent_node is None:
                    raise ParentNodeNotFoundError(f"Parent node '{new_parent}' not found in module '{module}'")
                if not self._can_node_action(new_parent_node, actor=effective_actor, permission="p"):
                    raise ParentWriteForbiddenError(f"Write to parent node '{new_parent}' is not allowed")
                new_parent_ancestors = new_parent_node.get("ancestors")
                if isinstance(new_parent_ancestors, list) and node_id in new_parent_ancestors:
                    raise ParentCycleDetectedError(
                        f"Parent node '{new_parent}' cannot be a descendant of node '{node_id}'"
                    )
            else:
                self._enforce_root_create_permission(module, actor=effective_actor)
                self._enforce_root_entity_allowed(module, entity)

            new_depth, new_ancestors = self._build_hierarchy_fields(
                module,
                entity,
                new_parent,
                parent_node=new_parent_node if new_parent is not None else None,
            )
            candidate["depth"] = new_depth
            candidate["ancestors"] = new_ancestors

        candidate["id"] = node_id
        candidate["entity"] = entity
        candidate["deleted"] = current.get("deleted", False)
        candidate["cdate"] = current.get("cdate")
        candidate["mdate"] = utc_now_iso()
        self._apply_acl_defaults(candidate, actor=effective_actor)

        self._validate_node_candidate(candidate, entity_schema)
        _remove_transient_password_values(candidate, entity_schema)

        updated = self._node_repo.replace_node(module, candidate)
        if updated is None:
            raise ConflictError("Node violates a unique index constraint")
        if not parent_changed:
            if self.hooks.has_hooks("after_patch", module=module, entity=entity):
                self.hooks.dispatch(
                    NodeHookContext(
                        event="after_patch",
                        module=module,
                        entity=entity,
                        node_id=node_id,
                        actor=deepcopy(actor),
                        effective_actor=deepcopy(effective_actor),
                        payload=deepcopy(hook_payload),
                        current=deepcopy(current),
                        candidate=deepcopy(candidate),
                        result=deepcopy(updated),
                    )
                )
            return self._get_node_via_query(module, node_id, entity=entity, actor=effective_actor)

        old_ancestors = current.get("ancestors")
        if not isinstance(old_ancestors, list):
            raise ValidationError(f"Node '{node_id}' has invalid hierarchy fields")
        old_depth = current.get("depth")
        new_depth = candidate.get("depth")
        if not isinstance(old_depth, int) or not isinstance(new_depth, int):
            raise ValidationError(f"Node '{node_id}' has invalid hierarchy fields")
        old_prefix_len = len([*old_ancestors, node_id])
        depth_delta = new_depth - old_depth
        new_prefix = [*new_ancestors, node_id]
        self._node_repo.update_descendants_hierarchy(
            module,
            node_id,
            new_prefix,
            old_prefix_len,
            depth_delta,
        )
        if self.hooks.has_hooks("after_patch", module=module, entity=entity):
            self.hooks.dispatch(
                NodeHookContext(
                    event="after_patch",
                    module=module,
                    entity=entity,
                    node_id=node_id,
                    actor=deepcopy(actor),
                    effective_actor=deepcopy(effective_actor),
                    payload=deepcopy(hook_payload),
                    current=deepcopy(current),
                    candidate=deepcopy(candidate),
                    result=deepcopy(updated),
                )
            )
        return self._get_node_via_query(module, node_id, entity=entity, actor=effective_actor)

    def _protect_acl_hidden_references_in_patch(
        self,
        module: str,
        entity_schema: dict[str, Any],
        *,
        current: dict[str, Any],
        payload: dict[str, Any],
        actor: dict[str, Any] | None,
    ) -> None:
        paths: list[_LinkPatchPath] = []
        array_nested_paths: list[_ArrayNestedLinkPatchPath] = []
        self._collect_link_patch_paths(
            entity_schema,
            current_value=current,
            path=(),
            payload_value=payload,
            paths=paths,
            array_nested_paths=array_nested_paths,
        )
        if "parent" in payload:
            paths.append(
                _LinkPatchPath(
                    path=("parent",),
                    target_entities=frozenset(self._entity_repo.get_module_schemas(module)),
                    target_module=module,
                    is_multi=False,
                )
            )
        if not paths and not array_nested_paths:
            return

        ids_by_module: dict[str, set[str]] = {}
        for item in paths:
            if not item.target_entities:
                continue
            current_value = _get_nested_value(current, item.path)
            current_ids = _reference_ids(current_value, is_multi=item.is_multi)
            ids_by_module.setdefault(item.target_module, set()).update(
                current_ids
            )
        unique_array_nested_paths = {
            (item.array_path, item.relative_path, item.target_entities, item.target_module, item.is_multi): item
            for item in array_nested_paths
        }
        array_nested_values: list[tuple[_ArrayNestedLinkPatchPath, list[str]]] = []
        for item in unique_array_nested_paths.values():
            current_array = _get_nested_value(current, item.array_path)
            values = _collect_link_values_in_array_branch(
                item.array_schema,
                current_array,
                item.relative_path,
                is_multi=item.is_multi,
            )
            array_nested_values.append((item, values))
            if item.target_entities:
                ids_by_module.setdefault(item.target_module, set()).update(values)

        active_nodes_by_module: dict[str, dict[str, dict[str, Any]]] = {}
        for target_module, ids in ids_by_module.items():
            if not ids:
                continue
            active_nodes_by_module[target_module] = {
                node["id"]: node
                for node in self._node_repo.find_active_by_ids(target_module, ids)
                if isinstance(node.get("id"), str) and isinstance(node.get("entity"), str)
            }

        blocked_array_paths = sorted(
            {
                item.array_path
                for item, values in array_nested_values
                if not _contains_all_reference_ids(
                    _collect_acl_hidden_link_references(
                        values,
                        active_nodes_by_module.get(item.target_module, {}),
                        item.target_entities,
                        actor=actor,
                        can_read=self._can_node_action,
                    ),
                    _collect_link_values_in_array_branch(
                        item.array_schema,
                        _get_nested_value(payload, item.array_path),
                        item.relative_path,
                        is_multi=item.is_multi,
                    ),
                )
            }
        )
        blocked_paths: set[tuple[str | int, ...]] = set(blocked_array_paths)
        for item in paths:
            current_value = _get_nested_value(current, item.path)
            payload_value = _get_nested_value(payload, item.path)
            hidden_ids = _collect_acl_hidden_link_references(
                _reference_ids(current_value, is_multi=item.is_multi),
                active_nodes_by_module.get(item.target_module, {}),
                item.target_entities,
                actor=actor,
                can_read=self._can_node_action,
            )
            submitted_ids = _reference_ids(payload_value, is_multi=item.is_multi)
            missing_ids = _missing_reference_ids(hidden_ids, submitted_ids)
            if item.is_multi and missing_ids and isinstance(payload_value, list):
                _set_nested_value(payload, item.path, [*payload_value, *missing_ids])
            elif missing_ids:
                blocked_paths.add(item.path)

        if blocked_paths:
            raise LinkPatchAclHiddenReferencesMissingError(
                details={
                    "field_errors": [
                        {
                            "location": list(path),
                            "message": "Value must retain ACL-hidden references",
                            "keyword": "acl_hidden_references",
                        }
                        for path in sorted(blocked_paths, key=lambda value: tuple(map(str, value)))
                    ]
                }
            )

    def _collect_link_patch_paths(
        self,
        schema: dict[str, Any],
        *,
        current_value: Any,
        path: tuple[str | int, ...],
        payload_value: Any,
        paths: list[_LinkPatchPath],
        array_nested_paths: list[_ArrayNestedLinkPatchPath],
        array_path: tuple[str, ...] | None = None,
        array_schema: dict[str, Any] | None = None,
        relative_path: tuple[str | None, ...] = (),
    ) -> None:
        unwrapped = unwrap_nullable(schema)
        meta = unwrapped.get("x-meta")
        semantic_type = meta.get("semantic-type") if isinstance(meta, dict) else None

        if semantic_type in {"Link", "LinkArray"}:
            target = meta.get("link") if isinstance(meta, dict) else None
            target_module = target.get("module") if isinstance(target, dict) else None
            target_entities = target.get("entities") if isinstance(target, dict) else None
            if (
                isinstance(target_module, str)
                and target_module
                and isinstance(target_entities, list)
                and (
                    semantic_type == "Link"
                    or isinstance(payload_value, list)
                    or payload_value is None
                    or payload_value is _MISSING
                )
            ):
                target_entities_set = frozenset(entity for entity in target_entities if isinstance(entity, str))
                if array_path is None:
                    if semantic_type == "Link" or isinstance(current_value, list):
                        paths.append(
                            _LinkPatchPath(
                                path=path,
                                target_entities=target_entities_set,
                                target_module=target_module,
                                is_multi=semantic_type == "LinkArray",
                            )
                        )
                else:
                    assert array_schema is not None
                    array_nested_paths.append(
                        _ArrayNestedLinkPatchPath(
                            array_path=array_path,
                            array_schema=array_schema,
                            relative_path=relative_path,
                            target_entities=target_entities_set,
                            target_module=target_module,
                            is_multi=semantic_type == "LinkArray",
                        )
                    )
            return

        if semantic_type == "Object" or (not path and unwrapped.get("type") == "object"):
            properties = unwrapped.get("properties")
            if not isinstance(properties, dict) or not isinstance(payload_value, dict):
                return
            current_properties = current_value if isinstance(current_value, dict) else {}
            for field_name, field_schema in properties.items():
                if isinstance(field_schema, dict) and (path or field_name in payload_value):
                    self._collect_link_patch_paths(
                        field_schema,
                        current_value=current_properties.get(field_name),
                        path=(*path, field_name),
                        payload_value=payload_value.get(field_name, _MISSING),
                        paths=paths,
                        array_nested_paths=array_nested_paths,
                        array_path=array_path,
                        array_schema=array_schema,
                        relative_path=(*relative_path, field_name) if array_path is not None else (),
                    )
            return

        if semantic_type != "Array" or not isinstance(payload_value, list):
            return
        items = unwrapped.get("items")
        if not isinstance(items, dict):
            return
        current_items = current_value if isinstance(current_value, list) else []
        next_array_path = array_path if array_path is not None else tuple(segment for segment in path if isinstance(segment, str))
        next_array_schema = array_schema if array_schema is not None else unwrapped
        next_relative_path = (*relative_path, None) if array_path is not None else (None,)
        for index, item in enumerate(payload_value):
            self._collect_link_patch_paths(
                items,
                current_value=current_items[index] if index < len(current_items) else None,
                path=(*path, index),
                payload_value=item,
                paths=paths,
                array_nested_paths=array_nested_paths,
                array_path=next_array_path,
                array_schema=next_array_schema,
                relative_path=next_relative_path,
            )

    def patch_acl(
        self,
        module: str,
        node_id: str,
        payload: dict[str, Any],
        *,
        recursive: bool = False,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RequestBodyInvalidError("ACL payload must be an object")
        self._validate_acl_payload_keys(payload)
        if not payload:
            raise AclPatchPayloadInvalidError("ACL patch payload must not be empty")

        current = self._node_repo.find_by_id(module, node_id, deleted=False)
        if current is None:
            raise NotFoundError(f"Node '{node_id}' in module '{module}' not found")

        nodes = self._node_repo.find_active_subtree(module, node_id) if recursive else [current]
        if not nodes:
            raise NotFoundError(f"Node '{node_id}' in module '{module}' not found")

        prepared: list[dict[str, Any]] = []
        root_effective_actor = actor
        for index, node in enumerate(nodes):
            entity = node.get("entity")
            if not isinstance(entity, str) or not entity:
                raise ValidationError(f"Node '{node_id}' in module '{module}' has invalid entity")
            entity_schema = self._entity_repo.get_schema(module, entity)
            if entity_schema is None:
                raise NotFoundError(f"Entity '{entity}' in module '{module}' not found")

            if not self._can_node_action(node, actor=actor, permission="w"):
                raise ValidationError(f"Write to node '{node['id']}' is not allowed")
            self._validate_patch_acl_input(payload, current=node, actor=actor)

            hook_payload = deepcopy(payload)
            hook_context = NodeHookContext(
                event="before_acl_patch",
                module=module,
                entity=entity,
                node_id=node["id"],
                actor=deepcopy(actor),
                payload=hook_payload,
                current=deepcopy(node),
            )
            self.hooks.dispatch(hook_context)
            effective_actor = hook_context.actor
            if index == 0:
                root_effective_actor = effective_actor
            self._validate_acl_payload_keys(hook_payload, from_hook=True)
            self._validate_patch_acl_input(hook_payload, current=node, actor=effective_actor)

            candidate = deepcopy(node)
            changed_fields: dict[str, Any] = {}
            for key, value in hook_payload.items():
                if candidate.get(key) != value:
                    candidate[key] = deepcopy(value)
                    changed_fields[key] = deepcopy(value)

            if not changed_fields:
                continue

            self._validate_owner_group_references(
                owner_id=candidate.get("owner") if "owner" in changed_fields else None,
                group_id=candidate.get("group") if "group" in changed_fields else None,
                actor=effective_actor,
            )
            candidate["mdate"] = utc_now_iso()
            changed_fields["mdate"] = candidate["mdate"]
            self._validate_node_candidate(candidate, entity_schema)
            prepared.append(
                {
                    "id": node["id"],
                    "fields": changed_fields,
                    "current": deepcopy(node),
                    "candidate": deepcopy(candidate),
                    "payload": deepcopy(changed_fields),
                    "effective_actor": deepcopy(effective_actor),
                    "entity": entity,
                }
            )

        self._node_repo.bulk_update_fields(
            module,
            [{"id": item["id"], "fields": item["fields"]} for item in prepared],
        )

        for item in prepared:
            result = self._node_repo.find_by_id(module, item["id"], deleted=False)
            if result is None:
                raise NotFoundError(f"Node '{item['id']}' in module '{module}' not found")
            if self.hooks.has_hooks("after_acl_patch", module=module, entity=item["entity"]):
                self.hooks.dispatch(
                    NodeHookContext(
                        event="after_acl_patch",
                        module=module,
                        entity=item["entity"],
                        node_id=item["id"],
                        actor=deepcopy(actor),
                        effective_actor=deepcopy(item["effective_actor"]),
                        payload=deepcopy(item["payload"]),
                        current=deepcopy(item["current"]),
                        candidate=deepcopy(item["candidate"]),
                        result=deepcopy(result),
                    )
                )

        root = self._get_node_via_query(module, node_id, entity=current["entity"], actor=root_effective_actor)
        return {"node": root, "updated_count": len(prepared)}

    def delete(
        self,
        module: str,
        node_id: str,
        *,
        actor: dict[str, Any] | None = None,
    ) -> int:
        current = self._node_repo.find_by_id(module, node_id, deleted=False)
        if current is None:
            raise NotFoundError(f"Node '{node_id}' in module '{module}' not found")
        entity = current.get("entity")
        if not isinstance(entity, str) or not entity:
            raise ValidationError(f"Node '{node_id}' in module '{module}' has invalid entity")
        if not self._can_node_action(current, actor=actor, permission="w"):
            raise ValidationError(f"Write to node '{node_id}' is not allowed")
        self._ensure_descendants_writable(module, node_id, actor=actor)

        nodes_to_delete = self._node_repo.find_active_subtree(module, node_id)
        for node in nodes_to_delete:
            node_entity = node.get("entity")
            if not isinstance(node_entity, str) or not node_entity:
                raise ValidationError(f"Node '{node.get('id')}' in module '{module}' has invalid entity")
            self.hooks.dispatch(
                NodeHookContext(
                    event="before_delete",
                    module=module,
                    entity=node_entity,
                    node_id=node.get("id"),
                    actor=deepcopy(actor),
                    current=deepcopy(node),
                )
            )

        deleted_count = self._node_repo.soft_delete_nodes(
            module,
            [node["id"] for node in nodes_to_delete],
            utc_now_iso(),
        )
        for node in nodes_to_delete:
            node_entity = node["entity"]
            if not self.hooks.has_hooks("after_delete", module=module, entity=node_entity):
                continue
            self.hooks.dispatch(
                NodeHookContext(
                    event="after_delete",
                    module=module,
                    entity=node_entity,
                    node_id=node["id"],
                    actor=deepcopy(actor),
                    current=deepcopy(node),
                    deleted_count=deleted_count,
                )
            )
        return deleted_count

    def _ensure_descendants_writable(
        self,
        module: str,
        node_id: str,
        *,
        actor: dict[str, Any] | None,
    ) -> None:
        permission_filter = build_node_permission_filter(actor, "w")
        if permission_filter is None:
            return
        denied_descendant = self._node_repo.find_one(
            module,
            {
                "deleted": False,
                "ancestors": node_id,
                "$nor": [permission_filter],
            },
            {"_id": 0, "id": 1},
        )
        if denied_descendant is not None:
            raise DescendantWriteForbiddenError()

    def _build_hierarchy_fields(
        self,
        module: str,
        entity: str,
        parent_id: str | None,
        *,
        parent_node: dict[str, Any] | None = None,
    ) -> tuple[int, list[str]]:
        if parent_id is None:
            return 0, []

        parent = parent_node
        if parent is None:
            parent = self._node_repo.find_by_id(module, parent_id, deleted=False)
        if parent is None:
            raise ParentNodeNotFoundError(f"Parent node '{parent_id}' not found in module '{module}'")

        parent_entity = parent.get("entity")
        parent_schema = self._entity_repo.get_schema(module, parent_entity)
        if parent_schema is None:
            raise ValidationError(
                f"Parent entity '{parent_entity}' has no schema in module '{module}'"
            )

        allowed_children = (
            parent_schema.get("x-meta", {})
            .get("children", {})
            .get("entities", [])
        )
        if entity not in allowed_children:
            raise EntityNotAllowedUnderParentError(
                f"Entity '{entity}' cannot be added under parent entity '{parent_entity}'"
            )

        parent_ancestors = parent.get("ancestors")
        parent_depth = parent.get("depth")
        if not isinstance(parent_ancestors, list) or not isinstance(parent_depth, int):
            raise ValidationError(f"Parent node '{parent_id}' has invalid hierarchy fields")

        return parent_depth + 1, [*parent_ancestors, parent_id]

    def _get_node_via_query(
        self,
        module: str,
        node_id: str,
        *,
        entity: str,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        nodes = self.query(
            module,
            {
                "filter": {"id": node_id, "entity": entity},
                "project": ["*"],
            },
            actor=actor,
        )
        if not nodes:
            raise NotFoundError(f"Node '{node_id}' in module '{module}' not found")
        return nodes[0]

    def _get_node_for_read(
        self,
        module: str,
        node_id: str,
        *,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Schema discovery is not a query event; hooks run on the final selection.
        node = self._node_repo.find_one(
            module,
            {"id": node_id, "deleted": False},
            {"_id": 0, "entity": 1, "owner": 1, "group": 1, "perm": 1},
        )
        if node is None or not self._can_node_action(node, actor=actor, permission="r"):
            raise NotFoundError(f"Node '{node_id}' in module '{module}' not found")
        return node

    def _build_default_read_project(
        self,
        entity_schema: dict[str, Any],
        *,
        actor: dict[str, Any] | None = None,
    ) -> list[str]:
        actor_level = ACTOR_ROLE_ORDER[normalize_actor_role(actor)]
        return [
            "*",
            "owner.*",
            "group.*",
            *self._collect_schema_link_wildcards(entity_schema, actor_level=actor_level),
        ]

    def _collect_schema_link_wildcards(
        self,
        schema: dict[str, Any],
        *,
        actor_level: int,
        path: tuple[str, ...] = (),
    ) -> list[str]:
        unwrapped = unwrap_nullable(schema)
        if not self._is_field_visible_for_actor(unwrapped, actor_level=actor_level):
            return []

        semantic_type = unwrapped.get("x-meta", {}).get("semantic-type")
        if semantic_type in {"Link", "LinkArray"} and path:
            return [f"{'.'.join(path)}.*"]

        if unwrapped.get("type") == "array":
            items = unwrapped.get("items")
            return self._collect_schema_link_wildcards(items, actor_level=actor_level, path=path) if isinstance(items, dict) else []

        properties = unwrapped.get("properties")
        if unwrapped.get("type") != "object" or not isinstance(properties, dict):
            return []

        paths: list[str] = []
        for field_name, child_schema in properties.items():
            if isinstance(child_schema, dict):
                paths.extend(
                    self._collect_schema_link_wildcards(
                        child_schema,
                        actor_level=actor_level,
                        path=(*path, field_name),
                    )
                )
        return list(dict.fromkeys(paths))

    def _is_field_visible_for_actor(self, field_schema: dict[str, Any], *, actor_level: int) -> bool:
        visibility_mode = field_schema.get("x-meta", {}).get("visibility-mode")
        required_level = FIELD_ACCESS_MODE_ORDER.get(visibility_mode, FIELD_ACCESS_MODE_ORDER["all"])
        return actor_level >= required_level

    def _enforce_write_mode(
        self,
        entity_schema: dict[str, Any],
        payload: dict[str, Any],
        *,
        actor: dict[str, Any] | None = None,
    ) -> None:
        for key, value in payload.items():
            if key in {
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
            }:
                continue
            field_schema = entity_schema.get("properties", {}).get(key)
            if not isinstance(field_schema, dict):
                continue
            self._enforce_write_mode_recursive(field_schema, value, path=key, actor=actor)

    def _enforce_write_mode_recursive(
        self,
        field_schema: dict[str, Any],
        value: Any,
        *,
        path: str,
        actor: dict[str, Any] | None = None,
    ) -> None:
        field_schema = unwrap_nullable(field_schema)
        write_mode = field_schema.get("x-meta", {}).get("write-mode")
        if isinstance(write_mode, str):
            actor_level = self._actor_access_level(actor)
            required_level = FIELD_ACCESS_MODE_ORDER.get(write_mode)
            if required_level is not None and actor_level < required_level:
                raise FieldWriteForbiddenError(f"Field '{path}' is not writable for current actor")

        if isinstance(value, dict):
            properties = field_schema.get("properties", {})
            if not isinstance(properties, dict):
                return
            for key, nested_value in value.items():
                nested_schema = properties.get(key)
                if not isinstance(nested_schema, dict):
                    continue
                self._enforce_write_mode_recursive(
                    nested_schema,
                    nested_value,
                    path=f"{path}.{key}",
                    actor=actor,
                )
            return

        if isinstance(value, list):
            items_schema = field_schema.get("items")
            if not isinstance(items_schema, dict):
                return
            for idx, nested_value in enumerate(value):
                self._enforce_write_mode_recursive(
                    items_schema,
                    nested_value,
                    path=f"{path}[{idx}]",
                    actor=actor,
                )

    def _actor_access_level(self, actor: dict[str, Any] | None) -> int:
        return ACTOR_ROLE_ORDER[normalize_actor_role(actor)]

    def _can_node_action(
        self,
        node: dict[str, Any],
        *,
        actor: dict[str, Any] | None,
        permission: str,
    ) -> bool:
        if permission not in {"r", "w", "p"}:
            return False
        if actor_has_role_at_least(actor, "superuser"):
            return True

        perm = node.get("perm")
        owner = node.get("owner")
        group = node.get("group")
        if not isinstance(perm, dict) or not isinstance(owner, str) or not isinstance(group, str):
            return False

        actor_user_id = actor.get("user_id") if isinstance(actor, dict) else None
        actor_groups_raw = actor.get("groups") if isinstance(actor, dict) else None
        actor_groups: set[str] = set()
        if isinstance(actor_groups_raw, list):
            for item in actor_groups_raw:
                if isinstance(item, str) and item:
                    actor_groups.add(item)

        if isinstance(actor_user_id, str) and actor_user_id == owner:
            return bool(perm.get("owner", {}).get(permission))
        if group in actor_groups:
            return bool(perm.get("group", {}).get(permission))
        return bool(perm.get("others", {}).get(permission))

    def _enforce_root_create_permission(
        self,
        module: str,
        *,
        actor: dict[str, Any] | None,
    ) -> None:
        module_doc = self._module_repo.get_module(module)
        if module_doc is None:
            raise NotFoundError(f"Module '{module}' not found")
        root_perm = module_doc.get("root_perm")
        root_owner = module_doc.get("root_owner")
        root_group = module_doc.get("root_group")
        if not isinstance(root_perm, dict):
            raise ValidationError(f"Module '{module}' has invalid root permissions")
        if not isinstance(root_owner, str) or not root_owner:
            raise ValidationError(f"Module '{module}' has invalid root owner")
        if not isinstance(root_group, str) or not root_group:
            raise ValidationError(f"Module '{module}' has invalid root group")
        stub = {
            "owner": root_owner,
            "group": root_group,
            "perm": root_perm,
        }
        if not self._can_node_action(stub, actor=actor, permission="p"):
            raise RootCreateForbiddenError(f"Root create in module '{module}' is not allowed")

    def _enforce_root_entity_allowed(self, module: str, entity: str) -> None:
        module_doc = self._module_repo.get_module(module)
        if module_doc is None:
            raise NotFoundError(f"Module '{module}' not found")
        allowed_entities = module_doc.get("root_children_entities")
        if not isinstance(allowed_entities, list):
            raise ValidationError(f"Module '{module}' has invalid root_children_entities")
        if not allowed_entities:
            return
        if entity not in allowed_entities:
            raise EntityNotAllowedInRootError(f"Entity '{entity}' cannot be added to module root")

    def _apply_acl_defaults(
        self,
        candidate: dict[str, Any],
        *,
        actor: dict[str, Any] | None = None,
        entity_schema: dict[str, Any] | None = None,
    ) -> None:
        user_id = actor.get("user_id") if isinstance(actor, dict) else None
        if not isinstance(candidate.get("owner"), str) or not candidate.get("owner"):
            if not isinstance(user_id, str) or not user_id:
                raise OwnerRequiredError(
                    "Field 'owner' must be provided or actor must include non-empty user_id"
                )
            candidate["owner"] = user_id

        primary_group = actor.get("primary_group") if isinstance(actor, dict) else None
        if not isinstance(candidate.get("group"), str) or not candidate.get("group"):
            if not isinstance(primary_group, str) or not primary_group:
                raise GroupRequiredError(
                    "Field 'group' must be provided or actor must include non-empty primary_group"
                )
            candidate["group"] = primary_group

        if not isinstance(candidate.get("perm"), dict):
            candidate["perm"] = self._resolve_default_perm(entity_schema)

    def _resolve_default_perm(self, entity_schema: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(entity_schema, dict):
            raise ValidationError("Entity schema is missing")
        default_perm = (
            entity_schema.get("x-meta", {})
            .get("perm", {})
            .get("default")
        )
        if not isinstance(default_perm, dict):
            raise ValidationError("Entity schema x-meta.perm.default is missing or invalid")
        return deepcopy(default_perm)

    def _validate_create_acl_input(
        self,
        payload: dict[str, Any],
        *,
        actor: dict[str, Any] | None = None,
    ) -> None:
        if actor_has_role_at_least(actor, "superuser"):
            return
        if "group" not in payload:
            candidate_group = None
        else:
            candidate_group = payload.get("group")
            if not isinstance(candidate_group, str) or not candidate_group:
                raise GroupRequiredError("Field 'group' must be a non-empty string")

        actor_user_id = actor.get("user_id") if isinstance(actor, dict) else None
        if "owner" in payload:
            candidate_owner = payload.get("owner")
            if not isinstance(candidate_owner, str) or not candidate_owner:
                raise OwnerRequiredError("Field 'owner' must be a non-empty string")
            if not isinstance(actor_user_id, str) or not actor_user_id or candidate_owner != actor_user_id:
                raise OwnerMustMatchActorError("Field 'owner' must be equal to actor.user_id for non-superuser")

        actor_groups_raw = actor.get("groups") if isinstance(actor, dict) else None
        actor_groups: set[str] = set()
        if isinstance(actor_groups_raw, list):
            for item in actor_groups_raw:
                if isinstance(item, str) and item:
                    actor_groups.add(item)

        if candidate_group is not None and candidate_group not in actor_groups:
            raise GroupNotInActorGroupsError("Field 'group' must be one of actor groups")

    def _validate_owner_group_references(
        self,
        *,
        owner_id: Any | None,
        group_id: Any | None,
        actor: dict[str, Any] | None = None,
    ) -> None:
        actor_user_id = actor.get("user_id") if isinstance(actor, dict) else None
        actor_primary_group = actor.get("primary_group") if isinstance(actor, dict) else None
        if owner_id is not None:
            if not isinstance(owner_id, str) or not owner_id:
                raise OwnerRequiredError("Field 'owner' must be a non-empty string")
            if not (isinstance(actor_user_id, str) and actor_user_id and owner_id == actor_user_id):
                owner_node = self._node_repo.find_one(
                    _USERS_MODULE,
                    {
                        "entity": _USERS_USER_ENTITY,
                        "deleted": False,
                        "id": owner_id,
                    },
                    {"_id": 1},
                )
                if owner_node is None:
                    raise OwnerNotFoundError(f"Owner '{owner_id}' not found or deleted")

        if group_id is not None:
            if not isinstance(group_id, str) or not group_id:
                raise GroupRequiredError("Field 'group' must be a non-empty string")
            if not (
                isinstance(actor_primary_group, str)
                and actor_primary_group
                and group_id == actor_primary_group
            ):
                group_node = self._node_repo.find_one(
                    _USERS_MODULE,
                    {
                        "entity": _USERS_GROUP_ENTITY,
                        "deleted": False,
                        "id": group_id,
                    },
                    {"_id": 1},
                )
                if group_node is None:
                    raise GroupNotFoundError(f"Group '{group_id}' not found or deleted")

    def _validate_node_candidate(
        self,
        candidate: dict[str, Any],
        entity_schema: dict[str, Any],
    ) -> None:
        full_schema = build_effective_node_schema(entity_schema)
        validator = Draft7Validator(full_schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(candidate), key=lambda e: list(e.path))
        if errors:
            raise make_document_validation_error(errors, message="Node validation failed")

    def _validate_acl_payload_keys(
        self,
        payload: dict[str, Any],
        *,
        from_hook: bool = False,
    ) -> None:
        invalid_fields = sorted(set(payload) - _ACL_FIELDS)
        if invalid_fields:
            if from_hook:
                raise AclPatchPayloadInvalidError(
                    "before_acl_patch may only change owner, group and perm",
                )
            raise AclPatchPayloadInvalidError(
                "ACL endpoint accepts only owner, group and perm",
            )

    def _validate_patch_acl_input(
        self,
        payload: dict[str, Any],
        *,
        current: dict[str, Any],
        actor: dict[str, Any] | None = None,
    ) -> None:
        if actor_has_role_at_least(actor, "superuser"):
            return

        actor_user_id = actor.get("user_id") if isinstance(actor, dict) else None
        current_owner = current.get("owner")
        is_owner = isinstance(actor_user_id, str) and actor_user_id and actor_user_id == current_owner

        if "owner" in payload:
            candidate_owner = payload.get("owner")
            if not isinstance(candidate_owner, str) or not candidate_owner:
                raise OwnerRequiredError("Field 'owner' must be a non-empty string")
            if candidate_owner != current_owner:
                raise OwnerChangeForbiddenError("Field 'owner' can only be changed by superuser")
        if "perm" in payload:
            candidate_perm = payload.get("perm")
            if candidate_perm != current.get("perm") and not is_owner:
                raise PermChangeForbiddenError("Field 'perm' can only be changed by superuser or node owner")
        if "group" in payload:
            candidate_group = payload.get("group")
            if not isinstance(candidate_group, str) or not candidate_group:
                raise GroupRequiredError("Field 'group' must be a non-empty string")
            if candidate_group != current.get("group"):
                if not is_owner:
                    raise GroupChangeForbiddenError("Field 'group' can only be changed by superuser or node owner")

                actor_groups_raw = actor.get("groups") if isinstance(actor, dict) else None
                actor_groups: set[str] = set()
                if isinstance(actor_groups_raw, list):
                    for item in actor_groups_raw:
                        if isinstance(item, str) and item:
                            actor_groups.add(item)

                if candidate_group not in actor_groups:
                    raise GroupNotInActorGroupsError("Field 'group' must be one of actor groups")


def _get_nested_value(value: Any, path: tuple[str | int, ...]) -> Any:
    current = value
    for segment in path:
        if isinstance(segment, str) and isinstance(current, dict):
            current = current.get(segment)
            continue
        if isinstance(segment, int) and isinstance(current, list) and 0 <= segment < len(current):
            current = current[segment]
            continue
        return None
    return current


def _set_nested_value(value: dict[str, Any], path: tuple[str | int, ...], next_value: Any) -> None:
    if not path:
        raise ValueError("Cannot replace root patch payload")

    current: Any = value
    for segment in path[:-1]:
        if isinstance(segment, str) and isinstance(current, dict):
            current = current.get(segment)
            continue
        if isinstance(segment, int) and isinstance(current, list) and 0 <= segment < len(current):
            current = current[segment]
            continue
        raise ValueError("Invalid LinkArray patch path")

    final_segment = path[-1]
    if isinstance(final_segment, str) and isinstance(current, dict):
        current[final_segment] = next_value
        return
    if isinstance(final_segment, int) and isinstance(current, list) and 0 <= final_segment < len(current):
        current[final_segment] = next_value
        return
    raise ValueError("Invalid LinkArray patch path")


def _collect_link_values_in_array_branch(
    schema: dict[str, Any],
    value: Any,
    relative_path: tuple[str | None, ...],
    *,
    is_multi: bool,
) -> list[str]:
    if not relative_path:
        return _reference_ids(value, is_multi=is_multi)

    segment, *remaining = relative_path
    unwrapped = unwrap_nullable(schema)
    meta = unwrapped.get("x-meta")
    semantic_type = meta.get("semantic-type") if isinstance(meta, dict) else None
    if segment is None:
        items = unwrapped.get("items")
        if semantic_type != "Array" or not isinstance(items, dict) or not isinstance(value, list):
            return []
        return [
            link_id
            for item in value
            for link_id in _collect_link_values_in_array_branch(
                items, item, tuple(remaining), is_multi=is_multi
            )
        ]

    properties = unwrapped.get("properties")
    if (
        not isinstance(segment, str)
        or not isinstance(properties, dict)
        or not isinstance(properties.get(segment), dict)
        or not isinstance(value, dict)
    ):
        return []
    return _collect_link_values_in_array_branch(
        properties[segment],
        value.get(segment),
        tuple(remaining),
        is_multi=is_multi,
    )


def _collect_acl_hidden_link_references(
    values: list[str],
    active_nodes: dict[str, dict[str, Any]],
    target_entities: frozenset[str],
    *,
    actor: dict[str, Any] | None,
    can_read: Callable[..., bool],
) -> list[str]:
    return [
        value
        for value in values
        if (node := active_nodes.get(value)) is not None
        and node.get("entity") in target_entities
        and not can_read(node, actor=actor, permission="r")
    ]


def _contains_all_reference_ids(required_ids: list[str], submitted_ids: list[str]) -> bool:
    return not (Counter(required_ids) - Counter(submitted_ids))


def _missing_reference_ids(required_ids: list[str], submitted_ids: list[Any]) -> list[str]:
    missing_counts = Counter(required_ids) - Counter(
        value for value in submitted_ids if isinstance(value, str)
    )
    missing_ids: list[str] = []
    for value in required_ids:
        if missing_counts[value] <= 0:
            continue
        missing_ids.append(value)
        missing_counts[value] -= 1
    return missing_ids


def _reference_ids(value: Any, *, is_multi: bool) -> list[str]:
    if is_multi:
        return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []
    return [value] if isinstance(value, str) and value else []


def _remove_transient_password_values(value: Any, schema: dict[str, Any]) -> bool:
    """Remove Password values recursively and return whether the value itself is transient."""
    unwrapped = unwrap_nullable(schema)
    meta = unwrapped.get("x-meta")
    semantic_type = meta.get("semantic-type") if isinstance(meta, dict) else None

    if semantic_type == "Password":
        return True

    if semantic_type == "Array":
        items = unwrapped.get("items")
        if not isinstance(items, dict):
            return False
        item_schema = unwrap_nullable(items)
        item_meta = item_schema.get("x-meta")
        item_semantic = item_meta.get("semantic-type") if isinstance(item_meta, dict) else None
        if item_semantic == "Password":
            return True
        if item_semantic == "Object" and isinstance(value, list):
            for item in value:
                _remove_transient_password_values(item, item_schema)
        return False

    properties = unwrapped.get("properties")
    if not isinstance(value, dict) or not isinstance(properties, dict):
        return False
    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, dict) or field_name not in value:
            continue
        if _remove_transient_password_values(value[field_name], field_schema):
            del value[field_name]
    return False
