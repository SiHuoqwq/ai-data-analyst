import hashlib
import json
from typing import Any

from pydantic import ValidationError

from app.v2.services.structured_response import StructuredResponseError


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def diagnose_structured_response(
    content: str,
    *,
    finish_reason: str | None,
    request_stage: str,
    error: StructuredResponseError | ValidationError | None,
    intent_mode: str | None = None,
) -> dict[str, Any]:
    parsed = None
    try:
        candidate = json.loads(content)
        if isinstance(candidate, dict):
            parsed = candidate
    except (json.JSONDecodeError, TypeError):
        pass

    validation_errors = []
    if isinstance(error, ValidationError):
        validation_errors = error.errors(
            include_url=False,
            include_input=False,
            include_context=False,
        )
    locations = [list(item["loc"]) for item in validation_errors]
    error_types = [item["type"] for item in validation_errors]

    if not content.strip():
        error_code = "EMPTY_STRUCTURED_RESPONSE"
    elif parsed is None:
        error_code = "INVALID_JSON"
    elif isinstance(error, ValidationError):
        error_code = "INTENT_SCHEMA_MISMATCH"
    elif error is not None:
        error_code = "INVALID_JSON"
    else:
        error_code = None

    return {
        "content_empty": not bool(content.strip()),
        "content_length": len(content),
        "finish_reason": finish_reason,
        "json_parse_success": parsed is not None,
        "top_level_keys": sorted(parsed) if parsed is not None else [],
        "top_level_value_types": (
            {key: _json_type(value) for key, value in parsed.items()}
            if parsed is not None
            else {}
        ),
        "validation_error_types": error_types,
        "validation_error_locations": locations,
        "missing_field_names": [
            str(item["loc"][-1])
            for item in validation_errors
            if item["type"] == "missing" and item["loc"]
        ],
        "extra_field_names": [
            str(item["loc"][-1])
            for item in validation_errors
            if item["type"] == "extra_forbidden" and item["loc"]
        ],
        "invalid_enum_field_names": [
            str(item["loc"][-1])
            for item in validation_errors
            if item["type"] in {"literal_error", "enum"} and item["loc"]
        ],
        "response_sha256": hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest(),
        "request_stage": request_stage,
        "intent_mode": intent_mode,
        "error_code": error_code,
    }
