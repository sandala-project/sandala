from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from jsonschema.exceptions import best_match

from sandala.core.errors import DocumentValidationError, SchemaValidationError


def make_document_validation_error(
    errors: Iterable[JsonSchemaValidationError],
    *,
    message: str | None = None,
) -> DocumentValidationError:
    items = list(errors)
    if not items:
        raise ValueError("At least one validation error is required")
    error_message = message or DocumentValidationError.default_message
    if len(items) > 1:
        error_message = "Document contains multiple validation errors"
    return DocumentValidationError(
        error_message,
        details={"validation_errors": [_normalize_validation_error(error) for error in items]},
    )


def make_schema_validation_error(
    errors: Iterable[JsonSchemaValidationError],
    *,
    message: str | None = None,
) -> SchemaValidationError:
    items = list(errors)
    if not items:
        raise ValueError("At least one validation error is required")
    error_message = message or SchemaValidationError.default_message
    if len(items) > 1:
        error_message = "Schema contains multiple validation errors"
    return SchemaValidationError(
        error_message,
        details={"validation_errors": [_normalize_validation_error(error) for error in items]},
    )


def _normalize_validation_error(error: JsonSchemaValidationError) -> dict[str, Any]:
    selected_error, path_prefix = _select_relevant_error(error)
    return {
        "path": list(_build_path(selected_error, prefix=path_prefix)),
        "validator": selected_error.validator or "unknown",
        "raw_message": selected_error.message,
    }


def _build_path(error: JsonSchemaValidationError, *, prefix: Iterable[Any] = ()) -> Iterable[Any]:
    path = [*prefix, *list(error.path)]
    if error.validator == "required":
        missing_field = _extract_required_field_name(error.message)
        if missing_field is not None:
            path.append(missing_field)
    return path


def _extract_required_field_name(message: str) -> str | None:
    match = re.match(r"^'(.+)' is a required property$", message)
    if match is None:
        return None
    return match.group(1)


def _select_relevant_error(
    error: JsonSchemaValidationError,
    *,
    base_prefix: tuple[Any, ...] = (),
) -> tuple[JsonSchemaValidationError, tuple[Any, ...]]:
    if error.validator not in {"anyOf", "oneOf"} or not error.context:
        return error, base_prefix

    relevant_errors = [item for item in error.context if not _is_null_branch_type_error(item)]
    if not relevant_errors or len(relevant_errors) == len(error.context):
        return error, base_prefix

    selected = best_match(relevant_errors) or relevant_errors[0]
    return _select_relevant_error(
        selected,
        base_prefix=(*base_prefix, *list(error.path)),
    )


def _is_null_branch_type_error(error: JsonSchemaValidationError) -> bool:
    return error.validator == "type" and error.schema == {"type": "null"}
