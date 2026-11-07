from __future__ import annotations

import hashlib
import secrets
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from sandala.core.errors import ValidationError


class SecurityService:
    def __init__(self):
        self._password_hasher = PasswordHasher()

    def normalize_username(self, value: Any, *, field_name: str = "username") -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"Field '{field_name}' must be a non-empty string")

        return value.strip().lower()

    def hash_password(self, raw_password: str) -> str:
        return self._password_hasher.hash(raw_password)

    def verify_password(self, raw_password: str, password_hash: str) -> bool:
        try:
            return self._password_hasher.verify(password_hash, raw_password)
        except (VerifyMismatchError, VerificationError):
            return False

    def generate_session_id(self) -> str:
        return secrets.token_urlsafe(32)

    def hash_session_id(self, session_id: str) -> str:
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()

    def generate_pat_token(self) -> str:
        return secrets.token_urlsafe(48)

    def hash_pat_token(self, raw_token: str) -> str:
        return self.hash_password(raw_token)

    def verify_pat_token(self, raw_token: str, token_hash: str) -> bool:
        return self.verify_password(raw_token, token_hash)
