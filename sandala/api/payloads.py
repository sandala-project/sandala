from __future__ import annotations

import json
from typing import Any

from flask import request

from sandala.core.errors import ParameterInvalidError, RequestBodyInvalidError


def require_json_object() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise RequestBodyInvalidError("Request body must be a JSON object")
    return payload


def require_wrapped_object(field: str) -> dict[str, Any]:
    payload = require_json_object()
    wrapped = payload.get(field)
    if not isinstance(wrapped, dict):
        raise RequestBodyInvalidError(f"Request body must contain '{field}' object")
    return wrapped


def get_optional_wrapped_object(field: str, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if payload is None:
        if request.data:
            raise RequestBodyInvalidError("Request body must be a JSON object")
        return {} if default is None else dict(default)
    if not isinstance(payload, dict):
        raise RequestBodyInvalidError("Request body must be a JSON object")
    if not payload:
        return {} if default is None else dict(default)

    wrapped = payload.get(field)
    if wrapped is None:
        raise RequestBodyInvalidError(f"Request body must contain '{field}' object")
    if not isinstance(wrapped, dict):
        raise RequestBodyInvalidError(f"Request body field '{field}' must be a JSON object")
    return wrapped


def wrap_resource(field: str, value: Any) -> dict[str, Any]:
    return {field: value}


def require_form_json_object(field: str) -> dict[str, Any]:
    raw = request.form.get(field)
    if raw is None or not raw.strip():
        raise ParameterInvalidError(f"Multipart form must contain field '{field}'")
    return _parse_form_json_object(raw, field=field)


def get_optional_form_json_object(field: str) -> dict[str, Any] | None:
    raw = request.form.get(field)
    if raw is None or not raw.strip():
        return None
    return _parse_form_json_object(raw, field=field)


def get_optional_query_project(field: str) -> str | list[Any] | None:
    raw = request.args.get(field)
    if raw == "*":
        return "*"
    return _get_optional_query_json_value(field, (str, list), "JSON string or JSON array")


def _parse_form_json_object(raw: str, *, field: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParameterInvalidError(f"Field '{field}' must contain valid JSON object") from exc
    if not isinstance(parsed, dict):
        raise ParameterInvalidError(f"Field '{field}' must contain valid JSON object")
    return parsed


def _get_optional_query_json_value(field: str, expected_type: type | tuple[type, ...], description: str):
    raw = request.args.get(field)
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParameterInvalidError(f"Query parameter '{field}' must contain valid {description}") from exc
    if not isinstance(parsed, expected_type):
        raise ParameterInvalidError(f"Query parameter '{field}' must contain valid {description}")
    return parsed
