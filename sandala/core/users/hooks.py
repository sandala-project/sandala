from __future__ import annotations

import re
from typing import Any

from sandala.core.access import actor_has_role_at_least
from sandala.core.errors import (
    AnonymousRegistrationDisabledError,
    AuthorizationError,
    DefaultGroupInvalidError,
    DefaultGroupDeletionForbiddenError,
    DefaultGroupNotFoundError,
    EmailAlreadyExistsError,
    EmailInvalidError,
    IdentityInUseError,
    ParameterInvalidError,
    PasswordHashDirectWriteForbiddenError,
    RequestBodyInvalidError,
    RoleAssignmentForbiddenError,
    SandalaError,
    SelfDeletionForbiddenError,
    LastSuperuserDeletionForbiddenError,
    UsernameAlreadyExistsError,
    UserGroupNotFoundError,
    ValidationError,
)
from sandala.core.services.node_hooks import NodeHookContext, NodeHookRegistry
from sandala.core.users.schemas import GROUP_ENTITY, USER_ENTITY, USER_MODULE

_ROLE_LEVELS: dict[str, int] = {
    "all": 0,
    "admin": 1,
    "superuser": 2,
}

_LOCAL_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$"
)
_DOMAIN_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")


class UsersUserNodeHooks:
    def __init__(self, node_repo, module_repo, security, config: dict[str, Any] | None = None):
        self._node_repo = node_repo
        self._module_repo = module_repo
        self._security = security
        self._config = config or {}
        self._allow_anonymous_registration = bool(
            self._config.get("ALLOW_ANONYMOUS_USER_REGISTRATION", False)
        )

    def before_create(self, context: NodeHookContext) -> None:
        payload = context.payload
        if not isinstance(payload, dict):
            raise RequestBodyInvalidError("Node payload must be an object")
        if "password_hash" in payload:
            raise PasswordHashDirectWriteForbiddenError("Field 'password_hash' cannot be provided directly")

        try:
            username = self._security.normalize_username(payload.get("username"))
        except ValidationError as exc:
            raise _with_field_error(exc, location=["username"], keyword="username_invalid")
        if self._username_exists(username):
            raise UsernameAlreadyExistsError(
                f"User with username '{username}' already exists",
                details=_field_error_details(["username"], "Username is already in use", "username_already_exists"),
            )

        try:
            email = _normalize_optional_email(payload.get("email"))
        except EmailInvalidError as exc:
            raise _with_field_error(exc, location=["email"], keyword="email_invalid")
        if email and self._email_exists(email):
            raise EmailAlreadyExistsError(
                f"User with email '{email}' already exists",
                details=_field_error_details(["email"], "Email is already in use", "email_already_exists"),
            )

        password_present = "password" in payload
        password = payload.get("password")
        if password_present and (not isinstance(password, str) or not password):
            raise ParameterInvalidError(
                "Field 'password' must be a non-empty string",
                details=_field_error_details(["password"], "Password must be a non-empty string", "password_invalid"),
            )

        try:
            role = _normalize_role(payload.get("role", "all"))
        except ParameterInvalidError as exc:
            raise _with_field_error(exc, location=["role"], keyword="role_invalid")
        if role in {"admin", "superuser"} and not actor_has_role_at_least(context.actor, "superuser"):
            raise RoleAssignmentForbiddenError(
                "Only superuser can assign admin or superuser role",
                details=_field_error_details(["role"], "Only a superuser can assign this role", "role_assignment_forbidden"),
            )

        try:
            primary_group = _normalize_optional_string(payload.get("primary_group"), field="primary_group")
        except ParameterInvalidError as exc:
            raise _with_field_error(exc, location=["primary_group"], keyword="primary_group_invalid")
        if primary_group is None:
            primary_group = self._resolve_default_group_id()

        try:
            groups = _normalize_groups(payload.get("groups"))
        except ParameterInvalidError as exc:
            raise _with_field_error(exc, location=["groups"], keyword="groups_invalid")
        groups = _ensure_group_in_list(groups, primary_group)
        self._validate_group_exists(primary_group, location=["primary_group"])
        self._validate_groups_exist(groups, known_existing_ids={primary_group})
        user_id = _normalize_required_string(payload.get("id"), field="id")

        payload["username"] = username
        payload["email"] = email
        if password_present:
            payload["password_hash"] = self._security.hash_password(password)
        payload["role"] = role
        payload["active"] = bool(payload.get("active", True))
        payload["primary_group"] = primary_group
        payload["groups"] = groups
        actor = context.actor if isinstance(context.actor, dict) else None
        actor_user_id = actor.get("user_id") if isinstance(actor, dict) else None
        is_anonymous = not isinstance(actor_user_id, str) or not actor_user_id.strip()
        if not is_anonymous:
            return
        if not self._allow_anonymous_registration:
            raise AnonymousRegistrationDisabledError("Anonymous user registration is disabled")

        payload["owner"] = user_id
        payload["group"] = primary_group
        context.actor = {
            "user_id": user_id,
            "primary_group": primary_group,
            "groups": groups,
            "role": role,
        }

    def before_patch(self, context: NodeHookContext) -> None:
        payload = context.payload
        if not isinstance(payload, dict):
            raise RequestBodyInvalidError("Node payload must be an object")
        if "password_hash" in payload:
            raise PasswordHashDirectWriteForbiddenError("Field 'password_hash' cannot be provided directly")

        current = context.current or {}
        current_id = current.get("id")

        if "username" in payload:
            try:
                username = self._security.normalize_username(payload.get("username"))
            except ValidationError as exc:
                raise _with_field_error(exc, location=["username"], keyword="username_invalid")
            if self._username_exists(username, exclude_user_id=current_id):
                raise UsernameAlreadyExistsError(
                    f"User with username '{username}' already exists",
                    details=_field_error_details(["username"], "Username is already in use", "username_already_exists"),
                )
            payload["username"] = username

        if "email" in payload:
            try:
                email = _normalize_optional_email(payload.get("email"))
            except EmailInvalidError as exc:
                raise _with_field_error(exc, location=["email"], keyword="email_invalid")
            if email and self._email_exists(email, exclude_user_id=current_id):
                raise EmailAlreadyExistsError(
                    f"User with email '{email}' already exists",
                    details=_field_error_details(["email"], "Email is already in use", "email_already_exists"),
                )
            payload["email"] = email

        if "password" in payload:
            password = payload.get("password")
            if password == "":
                payload.pop("password", None)
            elif not isinstance(password, str) or not password:
                raise ParameterInvalidError(
                    "Field 'password' must be a non-empty string",
                    details=_field_error_details(["password"], "Password must be a non-empty string", "password_invalid"),
                )
            else:
                payload["password_hash"] = self._security.hash_password(password)

        if "role" in payload:
            try:
                role = _normalize_role(payload.get("role"))
            except ParameterInvalidError as exc:
                raise _with_field_error(exc, location=["role"], keyword="role_invalid")
            if role in {"admin", "superuser"} and not actor_has_role_at_least(context.actor, "superuser"):
                raise RoleAssignmentForbiddenError(
                    "Only superuser can assign admin or superuser role",
                    details=_field_error_details(["role"], "Only a superuser can assign this role", "role_assignment_forbidden"),
                )
            payload["role"] = role

        if "primary_group" in payload:
            try:
                payload["primary_group"] = _normalize_required_string(
                    payload.get("primary_group"),
                    field="primary_group",
                )
            except ParameterInvalidError as exc:
                raise _with_field_error(exc, location=["primary_group"], keyword="primary_group_invalid")

        if "groups" in payload:
            try:
                payload["groups"] = _normalize_groups(payload.get("groups"))
            except ParameterInvalidError as exc:
                raise _with_field_error(exc, location=["groups"], keyword="groups_invalid")

        if "primary_group" in payload or "groups" in payload:
            primary_group = payload.get("primary_group", current.get("primary_group"))
            try:
                primary_group = _normalize_required_string(primary_group, field="primary_group")
            except ParameterInvalidError as exc:
                raise _with_field_error(exc, location=["primary_group"], keyword="primary_group_invalid")
            groups = payload.get("groups", current.get("groups", []))
            try:
                groups = _normalize_groups(groups)
            except ParameterInvalidError as exc:
                raise _with_field_error(exc, location=["groups"], keyword="groups_invalid")
            groups = _ensure_group_in_list(groups, primary_group)
            self._validate_group_exists(primary_group, location=["primary_group"])
            self._validate_groups_exist(groups, known_existing_ids={primary_group})
            payload["primary_group"] = primary_group
            payload["groups"] = groups

    def before_delete(self, context: NodeHookContext) -> None:
        current = context.current or {}
        user_id = _normalize_required_string(current.get("id"), field="id")
        actor = context.actor if isinstance(context.actor, dict) else None
        if actor is not None and actor.get("user_id") == user_id:
            raise SelfDeletionForbiddenError(f"User '{user_id}' cannot delete themselves")

        for module in self._module_repo.list_modules():
            module_name = module.get("name")
            if not isinstance(module_name, str) or not module_name:
                continue
            dependent = self._node_repo.find_one(
                module_name,
                {
                    "deleted": False,
                    "owner": user_id,
                    "$nor": [
                        {"id": user_id},
                        {"ancestors": user_id},
                    ],
                },
                {"_id": 0, "id": 1},
            )
            if dependent is not None:
                raise IdentityInUseError(
                    f"User '{user_id}' is still referenced as owner by node "
                    f"'{dependent.get('id')}' in module '{module_name}'",
                    details={
                        "identity_type": USER_ENTITY,
                        "identity_id": user_id,
                        "reference_type": "node.owner",
                        "module": module_name,
                        "node_id": dependent.get("id"),
                    },
                )

            if module.get("root_owner") == user_id:
                raise IdentityInUseError(
                    f"User '{user_id}' is still referenced as root_owner by module '{module_name}'",
                    details={
                        "identity_type": USER_ENTITY,
                        "identity_id": user_id,
                        "reference_type": "module.root_owner",
                        "module": module_name,
                    },
                )

    def before_delete_subtree(self, context: NodeHookContext) -> None:
        node_id = _normalize_required_string(context.node_id, field="id")
        superuser_query = {
            "entity": USER_ENTITY,
            "deleted": False,
            "role": "superuser",
            "active": True,
        }
        deleted_superuser = self._node_repo.find_one(
            USER_MODULE,
            {
                **superuser_query,
                "$or": [
                    {"id": node_id},
                    {"ancestors": node_id},
                ],
            },
            {"_id": 0, "id": 1},
        )
        if deleted_superuser is None:
            return

        remaining_superuser = self._node_repo.find_one(
            USER_MODULE,
            {
                **superuser_query,
                "$nor": [
                    {"id": node_id},
                    {"ancestors": node_id},
                ],
            },
            {"_id": 0, "id": 1},
        )
        if remaining_superuser is None:
            raise LastSuperuserDeletionForbiddenError("Deletion cannot leave the system without a superuser")

    def _validate_group_exists(self, group_id: str, *, location: list[str | int]) -> None:
        group = self._node_repo.find_one(
            USER_MODULE,
            {
                "entity": GROUP_ENTITY,
                "deleted": False,
                "id": group_id,
            },
            {"_id": 1},
        )
        if group is None:
            raise UserGroupNotFoundError(
                f"Group '{group_id}' not found or deleted",
                details=_field_error_details(location, "Selected group does not exist", "user_group_not_found"),
            )

    def _validate_groups_exist(self, group_ids: list[str], *, known_existing_ids: set[str] | None = None) -> None:
        for group_id in group_ids:
            if known_existing_ids is not None and group_id in known_existing_ids:
                continue
            group = self._node_repo.find_one(
                USER_MODULE,
                {
                    "entity": GROUP_ENTITY,
                    "deleted": False,
                    "id": group_id,
                },
                {"_id": 1},
            )
            if group is None:
                raise UserGroupNotFoundError(
                    f"Group '{group_id}' not found or deleted",
                    details=_field_error_details(["groups"], "One of the selected groups does not exist", "user_group_not_found"),
                )

    def _resolve_default_group_id(self) -> str:
        default_group = self._node_repo.find_one(
            USER_MODULE,
            {
                "entity": GROUP_ENTITY,
                "deleted": False,
                "is_default": True,
            },
            {"_id": 0, "id": 1},
        )
        if default_group is None:
            raise DefaultGroupNotFoundError("Default group with is_default=true not found")

        default_group_id = default_group.get("id")
        if not isinstance(default_group_id, str) or not default_group_id:
            raise DefaultGroupInvalidError("Default group has invalid id")
        return default_group_id

    def _username_exists(self, username: str, *, exclude_user_id: str | None = None) -> bool:
        query: dict[str, Any] = {
            "entity": USER_ENTITY,
            "username": username,
        }
        if exclude_user_id:
            query["id"] = {"$ne": exclude_user_id}
        return self._node_repo.find_one(USER_MODULE, query, {"_id": 1}) is not None

    def _email_exists(self, email: str, *, exclude_user_id: str | None = None) -> bool:
        query: dict[str, Any] = {
            "entity": USER_ENTITY,
            "email": email,
        }
        if exclude_user_id:
            query["id"] = {"$ne": exclude_user_id}
        return self._node_repo.find_one(USER_MODULE, query, {"_id": 1}) is not None


def register_users_module_node_hooks(
    hook_registry: NodeHookRegistry,
    node_repo,
    module_repo,
    security,
    config: dict[str, Any] | None = None,
) -> None:
    hooks = UsersUserNodeHooks(node_repo, module_repo, security, config)
    hook_registry.register(
        "before_delete",
        hooks.before_delete_subtree,
        module=USER_MODULE,
    )
    hook_registry.register(
        "before_create",
        hooks.before_create,
        module=USER_MODULE,
        entity=USER_ENTITY,
    )
    hook_registry.register(
        "before_patch",
        hooks.before_patch,
        module=USER_MODULE,
        entity=USER_ENTITY,
    )
    hook_registry.register(
        "before_delete",
        hooks.before_delete,
        module=USER_MODULE,
        entity=USER_ENTITY,
    )

    group_hooks = UsersGroupNodeHooks(node_repo, module_repo)
    hook_registry.register(
        "before_create",
        group_hooks.before_create,
        module=USER_MODULE,
        entity=GROUP_ENTITY,
    )
    hook_registry.register(
        "before_patch",
        group_hooks.before_patch,
        module=USER_MODULE,
        entity=GROUP_ENTITY,
    )
    hook_registry.register(
        "before_delete",
        group_hooks.before_delete,
        module=USER_MODULE,
        entity=GROUP_ENTITY,
    )


class UsersGroupNodeHooks:
    def __init__(self, node_repo, module_repo):
        self._node_repo = node_repo
        self._module_repo = module_repo

    def before_create(self, context: NodeHookContext) -> None:
        payload = context.payload
        if not isinstance(payload, dict):
            raise RequestBodyInvalidError("Node payload must be an object")
        payload["is_default"] = False

    def before_patch(self, context: NodeHookContext) -> None:
        payload = context.payload
        if not isinstance(payload, dict):
            raise RequestBodyInvalidError("Node payload must be an object")
        payload.pop("is_default", None)

    def before_delete(self, context: NodeHookContext) -> None:
        current = context.current or {}
        group_id = _normalize_required_string(current.get("id"), field="id")
        if current.get("is_default") is True:
            raise DefaultGroupDeletionForbiddenError(f"Default group '{group_id}' cannot be deleted")

        for module in self._module_repo.list_modules():
            module_name = module.get("name")
            if not isinstance(module_name, str) or not module_name:
                continue
            dependent = self._node_repo.find_one(
                module_name,
                {
                    "deleted": False,
                    "group": group_id,
                    "$nor": [
                        {"id": group_id},
                        {"ancestors": group_id},
                    ],
                },
                {"_id": 0, "id": 1},
            )
            if dependent is not None:
                raise IdentityInUseError(
                    f"Group '{group_id}' is still referenced by node "
                    f"'{dependent.get('id')}' in module '{module_name}'",
                    details={
                        "identity_type": GROUP_ENTITY,
                        "identity_id": group_id,
                        "reference_type": "node.group",
                        "module": module_name,
                        "node_id": dependent.get("id"),
                    },
                )

            if module.get("root_group") == group_id:
                raise IdentityInUseError(
                    f"Group '{group_id}' is still referenced as root_group by module '{module_name}'",
                    details={
                        "identity_type": GROUP_ENTITY,
                        "identity_id": group_id,
                        "reference_type": "module.root_group",
                        "module": module_name,
                    },
                )

        member = self._node_repo.find_one(
            USER_MODULE,
            {
                "entity": USER_ENTITY,
                "deleted": False,
                "$or": [
                    {"primary_group": group_id},
                    {"groups": group_id},
                ],
                "$nor": [
                    {"id": group_id},
                    {"ancestors": group_id},
                ],
            },
            {"_id": 0, "id": 1, "primary_group": 1, "groups": 1},
        )
        if member is None:
            return
        reference_type = "user.primary_group" if member.get("primary_group") == group_id else "user.groups"
        raise IdentityInUseError(
            f"Group '{group_id}' is still referenced by user '{member.get('id')}'",
            details={
                "identity_type": GROUP_ENTITY,
                "identity_id": group_id,
                "reference_type": reference_type,
                "module": USER_MODULE,
                "node_id": member.get("id"),
            },
        )


def _field_error_details(location: list[str | int], message: str, keyword: str) -> dict[str, Any]:
    return {
        "field_errors": [
            {
                "location": location,
                "message": message,
                "keyword": keyword,
            }
        ]
    }


def _with_field_error(error: SandalaError, *, location: list[str | int], keyword: str) -> SandalaError:
    error.details = _field_error_details(location, error.message, keyword)
    return error


def _normalize_optional_email(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise EmailInvalidError("Field 'email' must be a valid email string")

    raw_email = value.strip()
    if raw_email.count("@") != 1:
        raise EmailInvalidError("Field 'email' must be a valid email string")

    local_part, domain_part = raw_email.rsplit("@", 1)
    local_part = local_part.strip()
    domain_part = domain_part.strip()

    if not local_part or not domain_part:
        raise EmailInvalidError("Field 'email' must be a valid email string")
    if len(local_part) > 64:
        raise EmailInvalidError("Field 'email' local part is too long")
    if not _LOCAL_EMAIL_PATTERN.fullmatch(local_part):
        raise EmailInvalidError("Field 'email' local part is invalid")

    try:
        domain_ascii = domain_part.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise EmailInvalidError("Field 'email' domain is invalid") from exc

    domain_ascii = domain_ascii.lower()
    if len(domain_ascii) > 253:
        raise EmailInvalidError("Field 'email' domain is too long")

    labels = domain_ascii.split(".")
    if len(labels) < 2:
        raise EmailInvalidError("Field 'email' domain must include a top-level domain")
    for label in labels:
        if not label or len(label) > 63:
            raise EmailInvalidError("Field 'email' domain label is invalid")
        if label.startswith("-") or label.endswith("-"):
            raise EmailInvalidError("Field 'email' domain label is invalid")
        if not _DOMAIN_LABEL_PATTERN.fullmatch(label):
            raise EmailInvalidError("Field 'email' domain label is invalid")

    return f"{local_part.lower()}@{domain_ascii}"


def _normalize_role(value: Any, *, field: str = "role") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ParameterInvalidError(f"Field '{field}' must be one of: all, admin, superuser")
    normalized = value.strip().lower()
    if normalized not in _ROLE_LEVELS:
        raise ParameterInvalidError(f"Field '{field}' must be one of: all, admin, superuser")
    return normalized


def _normalize_optional_string(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ParameterInvalidError(f"Field '{field}' must be a non-empty string or null")
    return value.strip()


def _normalize_required_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ParameterInvalidError(f"Field '{field}' must be a non-empty string")
    return value.strip()


def _normalize_groups(value: Any) -> list[str]:
    groups = [] if value is None else value
    if not isinstance(groups, list) or any(not isinstance(item, str) or not item.strip() for item in groups):
        raise ParameterInvalidError("Field 'groups' must be an array of non-empty strings")
    return [item.strip() for item in groups]


def _ensure_group_in_list(groups: list[str], primary_group: str) -> list[str]:
    return list(dict.fromkeys([*groups, primary_group]))
