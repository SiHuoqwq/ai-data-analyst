import re
from typing import Any, Iterable

from app.db.models import FileModel
from app.v2.schemas.recommendations import RecommendationCandidate


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_SENSITIVE_FIELD = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"token|secret|password|passwd|credential|authorization|auth|private[_-]?key|"
    r"storage[_-]?key)(?:$|[^a-z0-9])"
)
_PATH_FIELD = re.compile(
    r"(?i)(?:^|[_\-\s])(?:file[_-]?path|filepath|path|directory|dir)(?:$|[_\-\s])"
)
_WINDOWS_PATH = re.compile(r"[A-Za-z]:[\\/]")
_POSIX_PATH = re.compile(r"(?<!\S)/(?:[^\s/]+/)+[^\s/]+")
_ROOT_FILE_PATH = re.compile(r"(?<!\S)/[^\s/]+")
_RELATIVE_PATH = re.compile(r"(?:^|\s)\.\.?[\\/]")
_UNSAFE_CONTENT = re.compile(
    r"(?ix)(?:"
    r"```|~~~|"
    r"\b(?:sql|python|pandas|numpy|subprocess|powershell|bash|shell|script)\b|"
    r"\b(?:select\s+.+?\s+from|insert\s+into|update\s+.+?\s+set|delete\s+from|"
    r"drop\s+(?:table|database)|alter\s+table|create\s+(?:table|database))\b|"
    r"\b(?:import\s+[a-z_]|from\s+[a-z_].*?\s+import|def\s+[a-z_]|class\s+[a-z_]|"
    r"function\s+[a-z_$])|"
    r"\b(?:run|execute|invoke|call|use)\s+(?:an?\s+|the\s+|this\s+)?(?:arbitrary\s+)?tool\b|"
    r"\b(?:system|developer)\s+(?:prompt|message)\b|"
    r"\bignore\s+(?:all\s+)?(?:previous|prior|system)\b|"
    r"\b(?:api[_\s-]*key|access[_\s-]*token|refresh[_\s-]*token|token|secret|"
    r"password|passwd|credential|authorization|bearer)\b|"
    r"__[a-z0-9_]+__|\b(?:print|exec|eval)\s*\("
    r")"
)


def safe_display_filename(filename: object, *, max_length: int = 255) -> str:
    """Return a control-free basename suitable for outbound display metadata."""
    normalized = _CONTROL_CHARACTERS.sub("", str(filename or ""))
    basename = normalized.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if basename in {"", ".", ".."}:
        basename = "uploaded-dataset"
    return basename[:max_length]


def is_public_field_name(field: object) -> bool:
    name = str(field or "").strip()
    if not name or _CONTROL_CHARACTERS.search(name):
        return False
    if any(character in name for character in ("/", "\\", ":")):
        return False
    return not (_SENSITIVE_FIELD.search(name) or _PATH_FIELD.search(name))


def public_column_metadata(
    columns_info: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        item
        for item in columns_info
        if is_public_field_name(item.get("name"))
    ]


def contains_unsafe_recommendation_content(
    candidate: RecommendationCandidate,
    file_record: FileModel,
) -> bool:
    parts = (candidate.label, candidate.question)
    if any(_CONTROL_CHARACTERS.search(part) for part in parts):
        return True
    text = " ".join(parts)
    if file_record.filepath and str(file_record.filepath) in text:
        return True
    if (
        _WINDOWS_PATH.search(text)
        or _POSIX_PATH.search(text)
        or _ROOT_FILE_PATH.search(text)
        or _RELATIVE_PATH.search(text)
        or "\\" in text
    ):
        return True
    if _UNSAFE_CONTENT.search(text):
        return True
    folded = text.casefold()
    private_fields = (
        str(item.get("name", ""))
        for item in (file_record.columns_info or [])
        if item.get("name") and not is_public_field_name(item.get("name"))
    )
    return any(field.casefold() in folded for field in private_fields)
