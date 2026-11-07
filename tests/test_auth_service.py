from __future__ import annotations

import pytest

from sandala.core.errors import AuthenticationError, AuthorizationError, NotFoundError, ValidationError
from sandala.core.services.auth_service import AuthService


class InMemoryIdentityRepo:
    def __init__(self, users):
        self._users = [dict(item) for item in users]

    def find_active_by_username_or_email(self, login):
        normalized = login.strip().lower()
        for user in self._users:
            if user.get("deleted") or not user.get("active"):
                continue
            if user.get("username") == normalized or user.get("email") == normalized:
                return dict(user)
        return None

    def find_by_id(self, user_id):
        for user in self._users:
            if user.get("id") == user_id and not user.get("deleted"):
                return dict(user)
        return None


class InMemoryAuthSessionRepo:
    def __init__(self, docs=None):
        self._docs = [dict(item) for item in (docs or [])]

    def create(self, session_doc):
        self._docs.append(dict(session_doc))
        return dict(session_doc)

    def find_active_by_hash(self, session_hash):
        for doc in self._docs:
            if doc.get("session_hash") == session_hash and doc.get("revoked_at") is None:
                return dict(doc)
        return None

    def renew_by_hash(self, session_hash, *, expires_at, mdate):
        for doc in self._docs:
            if doc.get("session_hash") == session_hash and doc.get("revoked_at") is None:
                doc["expires_at"] = expires_at
                doc["mdate"] = mdate
                return True
        return False

    def revoke_by_hash(self, session_hash, revoked_at):
        for doc in self._docs:
            if doc.get("session_hash") == session_hash and doc.get("revoked_at") is None:
                doc["revoked_at"] = revoked_at
                doc["mdate"] = revoked_at
                return True
        return False


class FailingRenewAuthSessionRepo(InMemoryAuthSessionRepo):
    def renew_by_hash(self, session_hash, *, expires_at, mdate):
        return False


class InMemoryPatRepo:
    def __init__(self, docs=None):
        self._docs = [dict(item) for item in (docs or [])]

    def create(self, pat_doc):
        self._docs.append(dict(pat_doc))
        return dict(pat_doc)

    def find_by_id(self, pat_id):
        for doc in self._docs:
            if doc.get("id") == pat_id:
                return dict(doc)
        return None

    def find_many(self, query=None):
        query = query or {}
        result = []
        for doc in self._docs:
            if all(doc.get(key) == value for key, value in query.items()):
                result.append(dict(doc))
        return result

    def update_by_id(self, pat_id, fields):
        for doc in self._docs:
            if doc.get("id") == pat_id:
                doc.update(fields)
                return True
        return False


class StubSecurity:
    def __init__(self):
        self._session_counter = 0
        self._pat_counter = 0

    def verify_password(self, raw_password, password_hash):
        return raw_password == "correct" and password_hash == "hash"

    def generate_session_id(self):
        self._session_counter += 1
        return f"session-{self._session_counter}"

    def hash_session_id(self, session_id):
        return f"hash-session:{session_id}"

    def generate_pat_token(self):
        self._pat_counter += 1
        return f"pat-secret-{self._pat_counter}"

    def hash_pat_token(self, raw_token):
        return f"hash-pat:{raw_token}"

    def verify_pat_token(self, raw_token, token_hash):
        return token_hash == f"hash-pat:{raw_token}"


def _service(users=None, session_docs=None, pat_docs=None, cfg=None):
    return AuthService(
        InMemoryIdentityRepo(users or []),
        InMemoryAuthSessionRepo(session_docs),
        InMemoryPatRepo(pat_docs),
        StubSecurity(),
        cfg or {
            "AUTH_SESSION_RENEWAL_ENABLED": False,
            "AUTH_SESSION_IDLE_TTL_SECONDS": 1209600,
            "AUTH_SESSION_ABSOLUTE_TTL_SECONDS": 1209600,
            "AUTH_SESSION_RENEWAL_WINDOW_SECONDS": 1800,
            "AUTH_PAT_DEFAULT_TTL_SECONDS": 1209600,
        },
    )


def _service_with_session_repo(session_repo, *, users=None, pat_docs=None, cfg=None):
    return AuthService(
        InMemoryIdentityRepo(users or []),
        session_repo,
        InMemoryPatRepo(pat_docs),
        StubSecurity(),
        cfg or {
            "AUTH_SESSION_RENEWAL_ENABLED": False,
            "AUTH_SESSION_IDLE_TTL_SECONDS": 1209600,
            "AUTH_SESSION_ABSOLUTE_TTL_SECONDS": 1209600,
            "AUTH_SESSION_RENEWAL_WINDOW_SECONDS": 1800,
            "AUTH_PAT_DEFAULT_TTL_SECONDS": 1209600,
        },
    )


def test_login_success_creates_session_and_actor():
    service = _service(
        users=[
            {
                "id": "user-1",
                "username": "alice",
                "email": "alice@example.com",
                "password_hash": "hash",
                "primary_group": "g1",
                "groups": ["g1"],
                "role": "all",
                "active": True,
                "deleted": False,
            }
        ]
    )

    result = service.login({"login": "alice", "password": "correct"})

    assert result["status"] == "ok"
    assert result["session_id"] == "session-1"
    assert result["actor"]["user_id"] == "user-1"
    assert result["actor"]["auth_type"] == "session"


def test_login_rejects_invalid_credentials():
    service = _service(
        users=[
            {
                "id": "user-1",
                "username": "alice",
                "password_hash": "hash",
                "active": True,
                "deleted": False,
            }
        ]
    )

    with pytest.raises(AuthenticationError):
        service.login({"login": "alice", "password": "wrong"})


def test_login_rejects_active_passwordless_user():
    service = _service(
        users=[
            {
                "id": "user-1",
                "username": "alice",
                "active": True,
                "deleted": False,
            }
        ]
    )

    with pytest.raises(AuthenticationError):
        service.login({"login": "alice", "password": "any-password"})


def test_authenticate_session_success():
    service = _service(
        users=[
            {
                "id": "user-1",
                "username": "alice",
                "primary_group": "g1",
                "groups": ["g1"],
                "role": "all",
                "active": True,
                "deleted": False,
            }
        ],
        session_docs=[
            {
                "session_hash": "hash-session:session-1",
                "user_id": "user-1",
                "expires_at": "2999-01-01T00:00:00Z",
                "max_expires_at": "2999-01-02T00:00:00Z",
                "revoked_at": None,
                "cdate": "2026-01-01T00:00:00Z",
                "mdate": "2026-01-01T00:00:00Z",
            }
        ],
    )

    actor = service.authenticate_session("session-1")
    assert actor["user_id"] == "user-1"
    assert actor["auth_type"] == "session"


def test_authenticate_bearer_success():
    service = _service(
        users=[
            {
                "id": "user-1",
                "username": "alice",
                "primary_group": "g1",
                "groups": ["g1"],
                "role": "all",
                "active": True,
                "deleted": False,
            }
        ],
        pat_docs=[
            {
                "id": "pat-1",
                "token_hash": "hash-pat:secret",
                "subject_id": "user-1",
                "name": "CLI",
                "expires_at": "2999-01-01T00:00:00Z",
                "revoked_at": None,
                "created_by": "user-1",
                "cdate": "2026-01-01T00:00:00Z",
                "mdate": "2026-01-01T00:00:00Z",
            }
        ],
    )

    actor = service.authenticate_bearer("pat-1.secret")
    assert actor["user_id"] == "user-1"
    assert actor["auth_type"] == "pat"


def test_authenticate_request_prefers_bearer_over_session():
    service = _service(
        users=[
            {
                "id": "user-1",
                "username": "alice",
                "primary_group": "g1",
                "groups": ["g1"],
                "role": "all",
                "active": True,
                "deleted": False,
            }
        ],
        session_docs=[
            {
                "session_hash": "hash-session:session-1",
                "user_id": "user-1",
                "expires_at": "2999-01-01T00:00:00Z",
                "max_expires_at": "2999-01-02T00:00:00Z",
                "revoked_at": None,
                "cdate": "2026-01-01T00:00:00Z",
                "mdate": "2026-01-01T00:00:00Z",
            }
        ],
        pat_docs=[
            {
                "id": "pat-1",
                "token_hash": "hash-pat:secret",
                "subject_id": "user-1",
                "name": "CLI",
                "expires_at": "2999-01-01T00:00:00Z",
                "revoked_at": None,
                "created_by": "user-1",
                "cdate": "2026-01-01T00:00:00Z",
                "mdate": "2026-01-01T00:00:00Z",
            }
        ],
    )

    result = service.authenticate_request(bearer_token="pat-1.secret", session_id="session-1")
    assert result["actor"]["auth_type"] == "pat"


def test_create_pat_for_self_returns_public_doc_with_token():
    service = _service(
        users=[
            {
                "id": "user-1",
                "username": "alice",
                "active": True,
                "deleted": False,
            }
        ]
    )

    result = service.create_pat(
        {"subject_id": "user-1", "name": "CLI"},
        actor={"user_id": "user-1", "role": "all"},
    )

    assert result["id"]
    assert result["token"].startswith(f"{result['id']}.")
    assert "_id" not in result
    assert "token_hash" not in result


def test_create_pat_for_other_user_requires_superuser():
    service = _service(
        users=[
            {
                "id": "user-2",
                "username": "bob",
                "active": True,
                "deleted": False,
            }
        ]
    )

    with pytest.raises(AuthorizationError):
        service.create_pat(
            {"subject_id": "user-2", "name": "CLI"},
            actor={"user_id": "user-1", "role": "admin"},
        )


def test_list_and_get_pat_are_limited_for_non_superuser():
    service = _service(
        pat_docs=[
            {
                "id": "pat-1",
                "token_hash": "hash-pat:secret",
                "subject_id": "user-1",
                "name": "CLI",
                "expires_at": None,
                "revoked_at": None,
                "created_by": "user-1",
                "cdate": "2026-01-01T00:00:00Z",
                "mdate": "2026-01-01T00:00:00Z",
            },
            {
                "id": "pat-2",
                "token_hash": "hash-pat:secret2",
                "subject_id": "user-2",
                "name": "Other",
                "expires_at": None,
                "revoked_at": None,
                "created_by": "user-2",
                "cdate": "2026-01-01T00:00:00Z",
                "mdate": "2026-01-01T00:00:00Z",
            },
        ]
    )

    items = service.list_pats(actor={"user_id": "user-1", "role": "all"})
    assert [item["id"] for item in items] == ["pat-1"]
    assert "token_hash" not in items[0]

    with pytest.raises(AuthorizationError):
        service.get_pat("pat-2", actor={"user_id": "user-1", "role": "all"})


def test_rotate_and_revoke_pat():
    service = _service(
        pat_docs=[
            {
                "id": "pat-1",
                "token_hash": "hash-pat:secret",
                "subject_id": "user-1",
                "name": "CLI",
                "expires_at": None,
                "revoked_at": None,
                "created_by": "user-1",
                "cdate": "2026-01-01T00:00:00Z",
                "mdate": "2026-01-01T00:00:00Z",
            }
        ]
    )

    rotated = service.rotate_pat("pat-1", actor={"user_id": "user-1", "role": "all"})
    assert rotated["token"].startswith("pat-1.")

    revoked = service.revoke_pat("pat-1", actor={"user_id": "user-1", "role": "all"})
    assert revoked["id"] == "pat-1"


def test_get_pat_raises_not_found():
    service = _service()

    with pytest.raises(NotFoundError):
        service.get_pat("missing", actor={"user_id": "user-1", "role": "superuser"})


def test_authenticate_session_renews_only_inside_window(monkeypatch):
    service = _service(
        users=[
            {
                "id": "user-1",
                "username": "alice",
                "primary_group": "g1",
                "groups": ["g1"],
                "role": "all",
                "active": True,
                "deleted": False,
            }
        ],
        session_docs=[
            {
                "session_hash": "hash-session:session-1",
                "user_id": "user-1",
                "expires_at": "2026-01-01T00:20:00Z",
                "max_expires_at": "2026-01-01T02:00:00Z",
                "revoked_at": None,
                "cdate": "2026-01-01T00:00:00Z",
                "mdate": "2026-01-01T00:00:00Z",
            }
        ],
        cfg={
            "AUTH_SESSION_RENEWAL_ENABLED": True,
            "AUTH_SESSION_IDLE_TTL_SECONDS": 3600,
            "AUTH_SESSION_ABSOLUTE_TTL_SECONDS": 7200,
            "AUTH_SESSION_RENEWAL_WINDOW_SECONDS": 1800,
            "AUTH_PAT_DEFAULT_TTL_SECONDS": 1209600,
        },
    )
    monkeypatch.setattr("sandala.core.services.auth_service.utc_now_iso", lambda: "2026-01-01T00:00:00Z")

    actor = service.authenticate_session("session-1")

    assert actor["user_id"] == "user-1"
    stored = service._auth_session_repo._docs[0]
    assert stored["expires_at"] == "2026-01-01T01:00:00Z"
    assert stored["mdate"] == "2026-01-01T00:00:00Z"


def test_authenticate_session_does_not_renew_outside_window(monkeypatch):
    service = _service(
        users=[
            {
                "id": "user-1",
                "username": "alice",
                "primary_group": "g1",
                "groups": ["g1"],
                "role": "all",
                "active": True,
                "deleted": False,
            }
        ],
        session_docs=[
            {
                "session_hash": "hash-session:session-1",
                "user_id": "user-1",
                "expires_at": "2026-01-01T05:00:00Z",
                "max_expires_at": "2026-01-01T10:00:00Z",
                "revoked_at": None,
                "cdate": "2026-01-01T00:00:00Z",
                "mdate": "2026-01-01T00:00:00Z",
            }
        ],
        cfg={
            "AUTH_SESSION_RENEWAL_ENABLED": True,
            "AUTH_SESSION_IDLE_TTL_SECONDS": 3600,
            "AUTH_SESSION_ABSOLUTE_TTL_SECONDS": 7200,
            "AUTH_SESSION_RENEWAL_WINDOW_SECONDS": 1800,
            "AUTH_PAT_DEFAULT_TTL_SECONDS": 1209600,
        },
    )
    monkeypatch.setattr("sandala.core.services.auth_service.utc_now_iso", lambda: "2026-01-01T00:00:00Z")

    service.authenticate_session("session-1")

    stored = service._auth_session_repo._docs[0]
    assert stored["expires_at"] == "2026-01-01T05:00:00Z"
    assert stored["mdate"] == "2026-01-01T00:00:00Z"


def test_authenticate_session_never_renews_past_absolute_limit(monkeypatch):
    service = _service(
        users=[
            {
                "id": "user-1",
                "username": "alice",
                "primary_group": "g1",
                "groups": ["g1"],
                "role": "all",
                "active": True,
                "deleted": False,
            }
        ],
        session_docs=[
            {
                "session_hash": "hash-session:session-1",
                "user_id": "user-1",
                "expires_at": "2026-01-01T00:20:00Z",
                "max_expires_at": "2026-01-01T00:40:00Z",
                "revoked_at": None,
                "cdate": "2026-01-01T00:00:00Z",
                "mdate": "2026-01-01T00:00:00Z",
            }
        ],
        cfg={
            "AUTH_SESSION_RENEWAL_ENABLED": True,
            "AUTH_SESSION_IDLE_TTL_SECONDS": 3600,
            "AUTH_SESSION_ABSOLUTE_TTL_SECONDS": 7200,
            "AUTH_SESSION_RENEWAL_WINDOW_SECONDS": 1800,
            "AUTH_PAT_DEFAULT_TTL_SECONDS": 1209600,
        },
    )
    monkeypatch.setattr("sandala.core.services.auth_service.utc_now_iso", lambda: "2026-01-01T00:00:00Z")

    service.authenticate_session("session-1")

    stored = service._auth_session_repo._docs[0]
    assert stored["expires_at"] == "2026-01-01T00:40:00Z"


def test_authenticate_session_rejects_absolute_expiry(monkeypatch):
    service = _service(
        users=[
            {
                "id": "user-1",
                "username": "alice",
                "primary_group": "g1",
                "groups": ["g1"],
                "role": "all",
                "active": True,
                "deleted": False,
            }
        ],
        session_docs=[
            {
                "session_hash": "hash-session:session-1",
                "user_id": "user-1",
                "expires_at": "2026-01-01T01:00:00Z",
                "max_expires_at": "2025-12-31T23:59:59Z",
                "revoked_at": None,
                "cdate": "2026-01-01T00:00:00Z",
                "mdate": "2026-01-01T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr("sandala.core.services.auth_service.utc_now_iso", lambda: "2026-01-01T00:00:00Z")

    with pytest.raises(AuthenticationError, match="Session is expired"):
        service.authenticate_session("session-1")


def test_authenticate_request_does_not_flag_renewal_when_repo_update_failed(monkeypatch):
    session_repo = FailingRenewAuthSessionRepo(
        [
            {
                "session_hash": "hash-session:session-1",
                "user_id": "user-1",
                "expires_at": "2026-01-01T00:20:00Z",
                "max_expires_at": "2026-01-01T02:00:00Z",
                "revoked_at": None,
                "cdate": "2026-01-01T00:00:00Z",
                "mdate": "2026-01-01T00:00:00Z",
            }
        ]
    )
    service = _service_with_session_repo(
        session_repo,
        users=[
            {
                "id": "user-1",
                "username": "alice",
                "primary_group": "g1",
                "groups": ["g1"],
                "role": "all",
                "active": True,
                "deleted": False,
            }
        ],
        cfg={
            "AUTH_SESSION_RENEWAL_ENABLED": True,
            "AUTH_SESSION_IDLE_TTL_SECONDS": 3600,
            "AUTH_SESSION_ABSOLUTE_TTL_SECONDS": 7200,
            "AUTH_SESSION_RENEWAL_WINDOW_SECONDS": 1800,
            "AUTH_PAT_DEFAULT_TTL_SECONDS": 1209600,
        },
    )
    monkeypatch.setattr("sandala.core.services.auth_service.utc_now_iso", lambda: "2026-01-01T00:00:00Z")

    result = service.authenticate_request(bearer_token=None, session_id="session-1")

    assert result["actor"]["user_id"] == "user-1"
    assert result["renew_session"] is False
