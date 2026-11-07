from __future__ import annotations

import os


DEFAULT_CONFIG = {
    "HOST": "0.0.0.0",
    "PORT": 3000,
    "MONGO_URI": "mongodb://localhost:27017",
    "MONGO_DB": "sandala",
    "AUTH_SESSION_RENEWAL_ENABLED": False,
    "AUTH_SESSION_IDLE_TTL_SECONDS": 1209600,
    "AUTH_SESSION_ABSOLUTE_TTL_SECONDS": 1209600,
    "AUTH_SESSION_RENEWAL_WINDOW_SECONDS": 1800,
    "AUTH_SESSION_COOKIE_NAME": "sandala_session",
    "AUTH_SESSION_COOKIE_DOMAIN": None,
    "AUTH_SESSION_COOKIE_PATH": "/",
    "AUTH_SESSION_COOKIE_SECURE": True,
    "AUTH_SESSION_COOKIE_HTTPONLY": True,
    "AUTH_SESSION_COOKIE_SAMESITE": "Lax",
    "AUTH_PAT_DEFAULT_TTL_SECONDS": 1209600,
    "AUTH_PASSWORD_MIN_LENGTH": 8,
    "AUTH_PASSWORD_PATTERN": r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[^A-Za-z0-9]).*$",
    "AUTH_USERNAME_MIN_LENGTH": 3,
    "AUTH_USERNAME_MAX_LENGTH": 32,
    "AUTH_USERNAME_PATTERN": r"^[a-z0-9._-]+$",
    "ROOT_USERNAME": "root",
    "ROOT_PASSWORD": "",
    "DEFAULT_GROUP_GROUPNAME": "default",
    "ALLOW_ANONYMOUS_USER_REGISTRATION": False,
    "HOOK_MODULES": [],
    "ADMIN_UI_DIST": None,
    "ASSET_STORAGE_BACKEND": "local_fs",
    "ASSET_LOCAL_ROOT": ".sandala_assets",
    "ASSET_PUBLIC_BASE_URL": None,
    "ASSET_S3_ENDPOINT": None,
    "ASSET_S3_BUCKET": "",
    "ASSET_S3_REGION": None,
    "ASSET_S3_ACCESS_KEY": None,
    "ASSET_S3_SECRET_KEY": None,
    "ASSET_S3_ADDRESSING_STYLE": "path",
}


def load_config_from_env() -> dict:
    cfg: dict = {}

    str_keys = [
        "HOST",
        "MONGO_URI",
        "MONGO_DB",
        "AUTH_SESSION_COOKIE_NAME",
        "AUTH_SESSION_COOKIE_DOMAIN",
        "AUTH_SESSION_COOKIE_PATH",
        "AUTH_SESSION_COOKIE_SAMESITE",
        "AUTH_PASSWORD_PATTERN",
        "AUTH_USERNAME_PATTERN",
        "ROOT_USERNAME",
        "ROOT_PASSWORD",
        "DEFAULT_GROUP_GROUPNAME",
        "ASSET_STORAGE_BACKEND",
        "ASSET_LOCAL_ROOT",
        "ASSET_PUBLIC_BASE_URL",
        "ASSET_S3_ENDPOINT",
        "ASSET_S3_BUCKET",
        "ASSET_S3_REGION",
        "ASSET_S3_ACCESS_KEY",
        "ASSET_S3_SECRET_KEY",
        "ASSET_S3_ADDRESSING_STYLE",
        "ADMIN_UI_DIST",
    ]
    int_keys = [
        "PORT",
        "AUTH_SESSION_IDLE_TTL_SECONDS",
        "AUTH_SESSION_ABSOLUTE_TTL_SECONDS",
        "AUTH_SESSION_RENEWAL_WINDOW_SECONDS",
        "AUTH_PAT_DEFAULT_TTL_SECONDS",
        "AUTH_PASSWORD_MIN_LENGTH",
        "AUTH_USERNAME_MIN_LENGTH",
        "AUTH_USERNAME_MAX_LENGTH",
    ]
    bool_keys = [
        "AUTH_SESSION_RENEWAL_ENABLED",
        "AUTH_SESSION_COOKIE_SECURE",
        "AUTH_SESSION_COOKIE_HTTPONLY",
        "ALLOW_ANONYMOUS_USER_REGISTRATION",
    ]

    for key in str_keys:
        raw = os.getenv(f"SANDALA_{key}")
        if raw is not None:
            cfg[key] = raw

    for key in int_keys:
        raw = os.getenv(f"SANDALA_{key}")
        if raw is None:
            continue
        try:
            cfg[key] = int(raw)
        except ValueError as exc:
            raise ValueError(f"Environment variable SANDALA_{key} must be an integer") from exc

    for key in bool_keys:
        raw = os.getenv(f"SANDALA_{key}")
        if raw is None:
            continue
        cfg[key] = _parse_bool(raw, env_key=f"SANDALA_{key}")

    hook_modules_raw = os.getenv("SANDALA_HOOK_MODULES")
    if hook_modules_raw is not None:
        cfg["HOOK_MODULES"] = _parse_hook_modules_csv(hook_modules_raw)

    return cfg


def build_config(override: dict | None = None) -> dict:
    cfg = {**DEFAULT_CONFIG, **load_config_from_env(), **(override or {})}
    cfg["HOOK_MODULES"] = normalize_hook_modules(cfg.get("HOOK_MODULES"))
    return cfg


def normalize_hook_modules(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _parse_hook_modules_csv(value)
    if isinstance(value, list):
        modules: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("HOOK_MODULES must contain only strings")
            stripped = item.strip()
            if stripped:
                modules.append(stripped)
        return modules
    raise ValueError("HOOK_MODULES must be a comma-separated string or list of strings")


def _parse_hook_modules_csv(raw: str) -> list[str]:
    return [name.strip() for name in raw.split(",") if name.strip()]


def _parse_bool(raw: str, *, env_key: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Environment variable {env_key} must be a boolean")
