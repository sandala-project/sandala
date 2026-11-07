ACTOR_ROLE_ORDER = {
    "all": 0,
    "admin": 1,
    "superuser": 2,
}

FIELD_ACCESS_MODE_ORDER = {
    "all": 0,
    "admin": 1,
    "superuser": 2,
    "none": 3,
}


def normalize_actor_role(actor) -> str:
    role = actor.get("role") if isinstance(actor, dict) else None
    if not isinstance(role, str):
        return "all"
    normalized = role.strip().lower()
    if normalized in ACTOR_ROLE_ORDER:
        return normalized
    return "all"


def actor_has_role_at_least(actor, required_role: str) -> bool:
    required_level = ACTOR_ROLE_ORDER.get(required_role)
    if required_level is None:
        raise ValueError(f"Unknown actor role '{required_role}'")
    return ACTOR_ROLE_ORDER[normalize_actor_role(actor)] >= required_level
