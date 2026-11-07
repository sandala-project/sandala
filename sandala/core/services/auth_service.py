from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from sandala.core.errors import (
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ParameterInvalidError,
    RequestBodyInvalidError,
    ValidationError,
)
from sandala.core.time_utils import iso_utc, parse_iso_utc, utc_now_iso


class AuthService:
    def __init__(
        self,
        identity_repo,
        auth_session_repo,
        pat_repo,
        security,
        config: dict[str, Any] | None = None,
    ):
        cfg = config or {}
        self._identity_repo = identity_repo
        self._auth_session_repo = auth_session_repo
        self._pat_repo = pat_repo
        self._security = security
        self._auth_session_renewal_enabled = bool(cfg.get("AUTH_SESSION_RENEWAL_ENABLED", False))
        self._auth_session_idle_ttl_seconds = int(cfg.get("AUTH_SESSION_IDLE_TTL_SECONDS", 1209600))
        self._auth_session_absolute_ttl_seconds = int(cfg.get("AUTH_SESSION_ABSOLUTE_TTL_SECONDS", 1209600))
        self._auth_session_renewal_window_seconds = int(cfg.get("AUTH_SESSION_RENEWAL_WINDOW_SECONDS", 1800))
        self._auth_pat_default_ttl_seconds = int(cfg.get("AUTH_PAT_DEFAULT_TTL_SECONDS", 1209600))

    def login(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RequestBodyInvalidError("Login request payload must be an object")

        login = payload.get("login")
        password = payload.get("password")
        if not isinstance(login, str) or not login.strip():
            raise ParameterInvalidError("Field 'login' must be a non-empty string")
        if not isinstance(password, str) or not password:
            raise ParameterInvalidError("Field 'password' must be a non-empty string")

        user = self._identity_repo.find_active_by_username_or_email(login)
        if user is None:
            raise AuthenticationError("Invalid login or password")

        password_hash = user.get("password_hash")
        if not isinstance(password_hash, str) or not self._security.verify_password(password, password_hash):
            raise AuthenticationError("Invalid login or password")

        raw_session_id = self._security.generate_session_id()
        now_iso = utc_now_iso()
        max_expires_at = _add_seconds(now_iso, self._auth_session_absolute_ttl_seconds)
        expires_at = _min_iso(
            _add_seconds(now_iso, self._auth_session_idle_ttl_seconds),
            max_expires_at,
        )
        self._auth_session_repo.create(
            {
                "session_hash": self._security.hash_session_id(raw_session_id),
                "user_id": user["id"],
                "expires_at": expires_at,
                "max_expires_at": max_expires_at,
                "revoked_at": None,
                "cdate": now_iso,
                "mdate": now_iso,
            }
        )

        return {
            "status": "ok",
            "session_id": raw_session_id,
            "actor": self._build_actor(user, auth_type="session"),
        }

    def logout(self, session_id: str | None) -> None:
        if not isinstance(session_id, str) or not session_id:
            return
        self._auth_session_repo.revoke_by_hash(
            self._security.hash_session_id(session_id),
            utc_now_iso(),
        )

    def authenticate_bearer(self, bearer_token: str) -> dict[str, Any]:
        return self._authenticate_bearer_result(bearer_token)["actor"]

    def authenticate_session(self, session_id: str) -> dict[str, Any]:
        return self._authenticate_session_result(session_id)["actor"]

    def authenticate_request(
        self,
        *,
        bearer_token: str | None,
        session_id: str | None,
    ) -> dict[str, Any] | None:
        if bearer_token is not None:
            return self._authenticate_bearer_result(bearer_token)
        if session_id is not None:
            return self._authenticate_session_result(session_id)
        return None

    def create_pat(self, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RequestBodyInvalidError("PAT request payload must be an object")

        subject_id = payload.get("subject_id")
        name = payload.get("name")
        expires_at = payload.get("expires_at", "__default__")

        if not isinstance(subject_id, str) or not subject_id:
            raise ParameterInvalidError("Field 'subject_id' must be a non-empty string")
        if not isinstance(name, str) or not name.strip():
            raise ParameterInvalidError("Field 'name' must be a non-empty string")

        self._assert_pat_subject_allowed(actor, subject_id)
        subject = self._identity_repo.find_by_id(subject_id)
        if subject is None or not subject.get("active", False):
            raise ValidationError("PAT subject must reference an active user")

        pat_id = str(uuid4())
        raw_secret = self._security.generate_pat_token()
        now_iso = utc_now_iso()
        doc = {
            "id": pat_id,
            "token_hash": self._security.hash_pat_token(raw_secret),
            "subject_id": subject_id,
            "name": name.strip(),
            "expires_at": self._normalize_pat_expires_at(expires_at, now_iso),
            "revoked_at": None,
            "created_by": actor["user_id"],
            "cdate": now_iso,
            "mdate": now_iso,
        }
        self._pat_repo.create(doc)
        return {**self._public_pat_doc(doc), "token": f"{pat_id}.{raw_secret}"}

    def list_pats(self, *, actor: dict[str, Any]) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if actor.get("role") != "superuser":
            query["subject_id"] = actor["user_id"]
        return [self._public_pat_doc(doc) for doc in self._pat_repo.find_many(query)]

    def get_pat(self, pat_id: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        return self._public_pat_doc(self._require_pat_visible(pat_id, actor=actor))

    def revoke_pat(self, pat_id: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        pat_doc = self._require_pat_visible(pat_id, actor=actor)
        now_iso = utc_now_iso()
        self._pat_repo.update_by_id(
            pat_id,
            {
                "revoked_at": now_iso,
                "mdate": now_iso,
            },
        )
        return {
            "id": pat_doc["id"],
            "revoked_at": now_iso,
            "mdate": now_iso,
        }

    def rotate_pat(self, pat_id: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        pat_doc = self._require_pat_visible(pat_id, actor=actor)
        if pat_doc.get("revoked_at") is not None:
            raise ValidationError("PAT is revoked")

        raw_secret = self._security.generate_pat_token()
        now_iso = utc_now_iso()
        self._pat_repo.update_by_id(
            pat_id,
            {
                "token_hash": self._security.hash_pat_token(raw_secret),
                "mdate": now_iso,
            },
        )
        return {
            "id": pat_id,
            "token": f"{pat_id}.{raw_secret}",
            "mdate": now_iso,
        }

    def _build_actor(self, user: dict[str, Any], *, auth_type: str) -> dict[str, Any]:
        return {
            "user_id": user["id"],
            "primary_group": user.get("primary_group"),
            "groups": user.get("groups", []),
            "role": user.get("role", "all"),
            "auth_type": auth_type,
        }

    def _assert_pat_subject_allowed(self, actor: dict[str, Any], subject_id: str) -> None:
        if actor.get("role") == "superuser":
            return
        if actor.get("user_id") != subject_id:
            raise AuthorizationError("PAT can only be created for the current user")

    def _require_pat_visible(self, pat_id: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        pat_doc = self._pat_repo.find_by_id(pat_id)
        if pat_doc is None:
            raise NotFoundError("PAT not found")
        if actor.get("role") == "superuser":
            return pat_doc
        if pat_doc.get("subject_id") != actor.get("user_id"):
            raise AuthorizationError("PAT is not accessible")
        return pat_doc

    def _normalize_pat_expires_at(self, value: Any, now_iso: str) -> str | None:
        if value == "__default__":
            return _add_seconds(now_iso, self._auth_pat_default_ttl_seconds)
        if value is None:
            return None
        if not isinstance(value, str) or not value:
            raise ParameterInvalidError("Field 'expires_at' must be a date-time string or null")
        try:
            parse_iso_utc(value)
        except ValueError as exc:
            raise ParameterInvalidError("Field 'expires_at' must be a valid ISO 8601 UTC string") from exc
        return value

    def _split_pat_token(self, bearer_token: str) -> tuple[str, str]:
        if not isinstance(bearer_token, str) or not bearer_token:
            raise AuthenticationError("Missing PAT")
        pat_id, separator, raw_secret = bearer_token.partition(".")
        if not separator or not pat_id or not raw_secret:
            raise AuthenticationError("Invalid PAT")
        return pat_id, raw_secret

    def _authenticate_bearer_result(self, bearer_token: str) -> dict[str, Any]:
        pat_id, raw_secret = self._split_pat_token(bearer_token)
        pat_doc = self._pat_repo.find_by_id(pat_id)
        if pat_doc is None:
            raise AuthenticationError("Invalid PAT")
        if pat_doc.get("revoked_at") is not None:
            raise AuthenticationError("PAT is revoked")

        expires_at = pat_doc.get("expires_at")
        if isinstance(expires_at, str) and _is_expired(expires_at):
            raise AuthenticationError("PAT is expired")

        token_hash = pat_doc.get("token_hash")
        if not isinstance(token_hash, str) or not self._security.verify_pat_token(raw_secret, token_hash):
            raise AuthenticationError("Invalid PAT")

        user = self._identity_repo.find_by_id(pat_doc["subject_id"])
        if user is None or not user.get("active", False):
            raise AuthenticationError("PAT subject is not active")

        return {
            "actor": self._build_actor(user, auth_type="pat"),
            "renew_session": False,
            "session_id": None,
        }

    def _authenticate_session_result(self, session_id: str) -> dict[str, Any]:
        if not isinstance(session_id, str) or not session_id:
            raise AuthenticationError("Missing session")

        session_hash = self._security.hash_session_id(session_id)
        session_doc = self._auth_session_repo.find_active_by_hash(session_hash)
        if session_doc is None:
            raise AuthenticationError("Invalid session")

        expires_at = session_doc.get("expires_at")
        max_expires_at = session_doc.get("max_expires_at")
        if not isinstance(expires_at, str) or _is_expired(expires_at):
            raise AuthenticationError("Session is expired")
        if not isinstance(max_expires_at, str) or _is_expired(max_expires_at):
            raise AuthenticationError("Session is expired")

        user = self._identity_repo.find_by_id(session_doc["user_id"])
        if user is None or not user.get("active", False):
            raise AuthenticationError("Session subject is not active")

        renewed = False
        now_iso = utc_now_iso()
        if self._should_renew_session(expires_at, now_iso):
            renewed_expires_at = _min_iso(
                _add_seconds(now_iso, self._auth_session_idle_ttl_seconds),
                max_expires_at,
            )
            if renewed_expires_at != expires_at:
                renewed = self._auth_session_repo.renew_by_hash(
                    session_hash,
                    expires_at=renewed_expires_at,
                    mdate=now_iso,
                )

        return {
            "actor": self._build_actor(user, auth_type="session"),
            "renew_session": renewed,
            "session_id": session_id,
        }

    def _should_renew_session(self, expires_at: str, now_iso: str) -> bool:
        if not self._auth_session_renewal_enabled:
            return False
        renewal_threshold = _add_seconds(now_iso, self._auth_session_renewal_window_seconds)
        return parse_iso_utc(expires_at) <= parse_iso_utc(renewal_threshold)

    def _public_pat_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        public_doc = dict(doc)
        public_doc.pop("_id", None)
        public_doc.pop("token_hash", None)
        return public_doc


def _is_expired(expires_at_iso: str) -> bool:
    try:
        expires_at = parse_iso_utc(expires_at_iso)
    except ValueError:
        return True
    return expires_at <= parse_iso_utc(utc_now_iso())


def _add_seconds(base_iso: str, seconds: int) -> str:
    return iso_utc(parse_iso_utc(base_iso) + timedelta(seconds=seconds))


def _min_iso(left: str, right: str) -> str:
    if parse_iso_utc(left) <= parse_iso_utc(right):
        return left
    return right
