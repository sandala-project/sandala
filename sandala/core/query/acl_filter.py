from __future__ import annotations

from typing import Any

from sandala.core.access import actor_has_role_at_least


def build_node_permission_filter(
    actor: dict[str, Any] | None,
    permission: str,
    *,
    owner_field: str = "owner",
    group_field: str = "group",
) -> dict[str, Any] | None:
    """Build a Mongo predicate for a node permission using Unix ACL precedence."""
    if permission not in {"r", "w", "p"}:
        raise ValueError(f"Unknown node permission '{permission}'")
    if actor_has_role_at_least(actor, "superuser"):
        return None

    actor_user_id = actor.get("user_id") if isinstance(actor, dict) else None
    if not isinstance(actor_user_id, str) or not actor_user_id:
        actor_user_id = "__sandala_no_actor_user__"

    actor_groups_raw = actor.get("groups") if isinstance(actor, dict) else None
    actor_groups: list[str] = []
    seen: set[str] = set()
    if isinstance(actor_groups_raw, list):
        for item in actor_groups_raw:
            if not isinstance(item, str):
                continue
            value = item.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            actor_groups.append(value)

    return {
        "$or": [
            {owner_field: {"$eq": actor_user_id}, f"perm.owner.{permission}": {"$eq": True}},
            {
                owner_field: {"$ne": actor_user_id},
                group_field: {"$in": actor_groups},
                f"perm.group.{permission}": {"$eq": True},
            },
            {
                owner_field: {"$ne": actor_user_id},
                group_field: {"$nin": actor_groups},
                f"perm.others.{permission}": {"$eq": True},
            },
        ]
    }
