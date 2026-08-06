import re
import unicodedata
from typing import Any, Iterable

from app.db.models import FileModel
from app.v2.schemas.recommendations import RecommendationCandidate


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_LOWER_TO_UPPER_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ACRONYM_BOUNDARY = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_SEMANTIC_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_SENSITIVE_TOKENS = {
    "auth",
    "authorization",
    "bearer",
    "credential",
    "password",
    "passwd",
    "secret",
    "token",
}
_SENSITIVE_COMPACT_MARKERS = (
    "apikey",
    "authorization",
    "bearer",
    "credential",
    "password",
    "passwd",
    "secret",
    "token",
)
_CREDENTIAL_QUALIFIERS = {
    "access",
    "api",
    "auth",
    "authentication",
    "authorization",
    "client",
    "private",
    "refresh",
    "secret",
    "session",
    "signing",
    "storage",
}
_CREDENTIAL_NOUNS = {"credential", "key", "password", "secret", "token"}
_PHYSICAL_LOCATION_QUALIFIERS = {
    "absolute",
    "directory",
    "download",
    "file",
    "filesystem",
    "local",
    "physical",
    "relative",
    "server",
    "source",
    "storage",
    "upload",
}
_PHYSICAL_LOCATION_NOUNS = {"location", "path", "uri", "url"}
_ALWAYS_PRIVATE_PATH_TOKENS = {"dir", "directory", "dirname", "filepath"}
_WINDOWS_PATH = re.compile(r"[A-Za-z]:[\\/]")
_POSIX_PATH = re.compile(r"/(?:[^\s/()]+/)+[^\s/()]+")
_ROOT_FILE_PATH = re.compile(r"(?<![A-Za-z0-9])/(?!/)[^\s/()]+")
_RELATIVE_PATH = re.compile(r"(?<![A-Za-z0-9])\.\.?[\\/]")
_RELATIVE_FILE_PATH = re.compile(
    r"(?i)(?<![\w.-])(?:[\w.-]+[\\/])+[\w.-]+\."
    r"(?:csv|tsv|xls|xlsx|json|parquet|feather|sqlite|db|txt)\b"
)
_SQL_CONTENT = re.compile(
    r"(?isx)(?:"
    r"\bselect\b.{0,200}?\bfrom\b|"
    r"\binsert\s+into\b|\bupdate\b.{0,200}?\bset\b|"
    r"\bdelete\s+from\b|\bmerge\s+into\b|\breplace\s+into\b|"
    r"\bupsert\s+into\b|"
    r"\b(?:create|alter|drop|truncate)\s+"
    r"(?:table|database|schema|view|index|sequence|user|role)\b|"
    r"\bcomment\s+on\s+(?:table|column|view|index|sequence)\b|"
    r"\bset\s+(?:role|session\s+authorization)\b|"
    r"\bgrant\b.{0,200}?\bto\b|\brevoke\b.{0,200}?\bfrom\b|"
    r"\bdeny\b.{0,200}?\bto\b|\b(?:call|execute)\s+[a-z_]"
    r")"
)
_UNSAFE_CONTENT = re.compile(
    r"(?imx)(?:"
    r"```|~~~|"
    r"\b(?:use|run|execute|invoke|call)\s+"
    r"(?:(?:an?|the|this)\s+)?"
    r"\b(?:sql|python|pandas|numpy|subprocess|powershell|bash|shell|script|code|query)\b|"
    r"\b(?:write|generate)\b.{0,40}?\b(?:script|code|query)\b|"
    r"\b(?:python3?|powershell|pwsh|bash|sh|cmd(?:\.exe)?)\s+(?:-[a-z]+|/[a-z]+)\b|"
    r"\b(?:import\s+[a-z_]|from\s+[a-z_].*?\s+import|def\s+[a-z_]|class\s+[a-z_]|"
    r"function\s+[a-z_$])|"
    r"\b(?:const|let|var)\s+[a-z_$][a-z0-9_$]*\s*=|=>|"
    r"\b(?:os|subprocess)\s*\.\s*[a-z_][a-z0-9_]*\b|"
    r"\b(?:os|subprocess)\s*\[\s*['\"][a-z_][a-z0-9_]*['\"]\s*\]|"
    r"\blambda\b(?:\s+[a-z_][a-z0-9_]*)?\s*:|"
    r"\b(?:system|popen|spawn)\s*\(|"
    r"\b[a-z_$][a-z0-9_$]*(?:\s*\.\s*[a-z_$][a-z0-9_$]*)+\s*\(|"
    r"\b[a-z_$][a-z0-9_$]*\(|"
    r"\b(?:open|print|exec|eval|compile|__import__)\s*\(|"
    r"\b(?:rm|rmdir|del|erase|chmod|chown|sudo|curl|wget)\s+"
    r"(?:-[a-z]+\s+)?\S+|"
    r"\$\(|"
    r"^\s*(?:sudo\s+)?(?:cat|echo|grep|ls|pwd|chmod|chown|cp|mv)\b(?:\s+\S+)+|"
    r"^\s*whoami\s*$|"
    r"\b(?:run|execute|invoke|call|use|open|launch|access)\b.{0,40}?"
    r"\b(?:tool|plugin|connector|terminal|shell|browser)\b|"
    r"\b(?:system|developer)\s+(?:prompt|message)\b|"
    r"\b(?:hidden|internal|private|system|developer)\s+"
    r"(?:prompt|instructions|message)\b|"
    r"\b(?:read|open|load|inspect|access)\s+(?:the\s+)?"
    r"(?:[a-z0-9_.-]+[\\/])+[a-z0-9_.-]+\b|"
    r"\bignore\s+(?:all\s+)?(?:previous|prior|system)\b|"
    r"\b(?:reveal|show|extract|read|print|return|expose)\b.{0,60}?"
    r"\b(?:prompt|instructions|api[_\s.-]*key|token|secret|password|credential)\b|"
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


def _semantic_tokens(value: object) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    normalized = _ACRONYM_BOUNDARY.sub(" ", normalized)
    normalized = _LOWER_TO_UPPER_BOUNDARY.sub(" ", normalized)
    return tuple(_SEMANTIC_TOKEN.findall(normalized.casefold()))


def _has_combined_semantics(
    tokens: tuple[str, ...],
    compact: str,
    qualifiers: set[str],
    nouns: set[str],
) -> bool:
    token_set = set(tokens)
    if token_set.intersection(qualifiers) and token_set.intersection(nouns):
        return True
    return any(
        qualifier + noun in compact or noun + qualifier in compact
        for qualifier in qualifiers
        for noun in nouns
    )


def is_public_field_name(field: object) -> bool:
    name = unicodedata.normalize("NFKC", str(field or "")).strip()
    if not name or _CONTROL_CHARACTERS.search(name):
        return False
    if any(character in name for character in ("/", "\\", ":")):
        return False
    tokens = _semantic_tokens(name)
    compact = "".join(tokens)
    if any(token in _SENSITIVE_TOKENS for token in tokens):
        return False
    if any(marker in compact for marker in _SENSITIVE_COMPACT_MARKERS):
        return False
    if _has_combined_semantics(
        tokens,
        compact,
        _CREDENTIAL_QUALIFIERS,
        _CREDENTIAL_NOUNS,
    ):
        return False
    if any(
        token in _ALWAYS_PRIVATE_PATH_TOKENS
        or token.startswith(("directory", "dirname", "filepath"))
        for token in tokens
    ):
        return False
    if compact == "path":
        return False
    return not _has_combined_semantics(
        tokens,
        compact,
        _PHYSICAL_LOCATION_QUALIFIERS,
        _PHYSICAL_LOCATION_NOUNS,
    )


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
    text = unicodedata.normalize("NFKC", "\n".join(parts))
    filepath = unicodedata.normalize("NFKC", str(file_record.filepath or ""))
    if filepath and filepath in text:
        return True
    if (
        _WINDOWS_PATH.search(text)
        or _POSIX_PATH.search(text)
        or _ROOT_FILE_PATH.search(text)
        or _RELATIVE_PATH.search(text)
        or _RELATIVE_FILE_PATH.search(text)
        or "\\" in text
    ):
        return True
    if _SQL_CONTENT.search(text) or _UNSAFE_CONTENT.search(text):
        return True
    folded = "".join(_semantic_tokens(text))
    private_fields = (
        "".join(_semantic_tokens(item.get("name", "")))
        for item in (file_record.columns_info or [])
        if item.get("name") and not is_public_field_name(item.get("name"))
    )
    return any(field and field in folded for field in private_fields)
