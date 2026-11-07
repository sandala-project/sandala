from __future__ import annotations

import re
from typing import Any

from flask import Flask, current_app, jsonify
from werkzeug.exceptions import HTTPException

from sandala.core.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    SandalaError,
    ValidationError,
)


def register_error_handlers(app: Flask) -> None:
    app.register_error_handler(SandalaError, _handle_sandala_error)
    app.register_error_handler(HTTPException, _handle_http_exception)
    app.register_error_handler(Exception, _handle_unexpected_error)


def _handle_sandala_error(exc: SandalaError):
    payload, status = serialize_api_error(exc)
    return jsonify(payload), status


def _handle_http_exception(exc: HTTPException):
    return exc


def _handle_unexpected_error(exc: Exception):
    current_app.logger.exception("Unhandled exception during request", exc_info=exc)
    payload = {
        "error": "internal_error",
        "error_description": "Internal server error",
    }
    return jsonify(payload), 500


def serialize_api_error(exc: SandalaError) -> tuple[dict[str, Any], int]:
    payload: dict[str, Any] = {
        "error": exc.code,
        "error_description": _error_description_for_api(exc),
    }
    details = _details_for_api(exc)
    if details is not None:
        payload["details"] = details
    return payload, _status_for_error(exc)


def _status_for_error(exc: SandalaError) -> int:
    if isinstance(exc, ValidationError):
        return 400
    if isinstance(exc, AuthenticationError):
        return 401
    if isinstance(exc, AuthorizationError):
        return 403
    if isinstance(exc, NotFoundError):
        return 404
    if isinstance(exc, ConflictError):
        return 409
    return 500


def _details_for_api(exc: SandalaError) -> dict[str, Any] | None:
    if exc.details is None:
        return None
    validation_errors = exc.details.get("validation_errors")
    if not isinstance(validation_errors, list):
        return exc.details

    details = {key: value for key, value in exc.details.items() if key != "validation_errors"}
    details["field_errors"] = [_serialize_validation_error(item) for item in validation_errors]
    return details


def _error_description_for_api(exc: SandalaError) -> str:
    validation_errors = exc.details.get("validation_errors") if isinstance(exc.details, dict) else None
    if not isinstance(validation_errors, list) or not validation_errors:
        return exc.message

    if len(validation_errors) == 1:
        error = validation_errors[0]
        path = error.get("path") if isinstance(error, dict) else None
        raw_message = error.get("raw_message") if isinstance(error, dict) else None
        if isinstance(path, list) and path:
            location = ".".join(str(item) for item in path)
            return f"{exc.message} at '{location}': {raw_message}"
        return f"{exc.message}: {raw_message}"

    return exc.message


def _serialize_validation_error(error: Any) -> dict[str, Any]:
    if not isinstance(error, dict):
        return {
            "location": [],
            "message": "Validation failed",
            "keyword": "unknown",
        }

    raw_message = error.get("raw_message")
    keyword = error.get("validator")
    location = error.get("path")
    return {
        "location": location if isinstance(location, list) else [],
        "message": _normalize_validation_message(keyword, raw_message),
        "keyword": keyword if isinstance(keyword, str) else "unknown",
    }


def _normalize_validation_message(keyword: Any, raw_message: Any) -> str:
    if not isinstance(raw_message, str):
        return "Validation failed"
    if keyword == "required":
        match = re.match(r"^'(.+)' is a required property$", raw_message)
        if match is not None:
            return f"Field '{match.group(1)}' is required"
    return raw_message
