import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


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
    "user",
}
_CREDENTIAL_NOUNS = {
    "certificate",
    "cookie",
    "credential",
    "key",
    "password",
    "secret",
    "token",
}
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
_PHYSICAL_LOCATION_NOUNS = {"folder", "location", "path", "uri", "url"}
_ALWAYS_PRIVATE_PATH_TOKENS = {"dir", "directory", "dirname", "filepath"}


@dataclass(frozen=True)
class _CompactWindowMatcher:
    exact_values: frozenset[str]
    exact_lengths: frozenset[int]
    max_token_count: int
    max_compact_characters: int


def _compact_window_matcher(values: Iterable[str]) -> _CompactWindowMatcher:
    exact_values = frozenset(values)
    exact_lengths = frozenset(len(value) for value in exact_values)
    max_compact_characters = max(exact_lengths)
    # A semantic token contains at least one compact character, so even a
    # deliberately one-character split cannot span more tokens than this.
    return _CompactWindowMatcher(
        exact_values=exact_values,
        exact_lengths=exact_lengths,
        max_token_count=max_compact_characters,
        max_compact_characters=max_compact_characters,
    )


def _compound_values(qualifiers: set[str], nouns: set[str]) -> frozenset[str]:
    return frozenset(
        compound
        for qualifier in qualifiers
        for noun in nouns
        for compound in (qualifier + noun, noun + qualifier)
    )


_SENSITIVE_COMPACT_MATCHER = _compact_window_matcher(_SENSITIVE_TOKENS)
_CREDENTIAL_COMPACT_MATCHER = _compact_window_matcher(
    _compound_values(_CREDENTIAL_QUALIFIERS, _CREDENTIAL_NOUNS)
)
_PHYSICAL_LOCATION_COMPACT_MATCHER = _compact_window_matcher(
    _compound_values(_PHYSICAL_LOCATION_QUALIFIERS, _PHYSICAL_LOCATION_NOUNS)
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


def _has_exact_semantics(
    tokens: Sequence[str],
    matcher: _CompactWindowMatcher,
) -> bool:
    return _has_exact_compact_window(tokens, matcher)


def _has_exact_compact_window(
    tokens: Sequence[str],
    matcher: _CompactWindowMatcher,
) -> bool:
    token_count = len(tokens)
    for start in range(token_count):
        compact = ""
        compact_characters = 0
        bounded_end = min(token_count, start + matcher.max_token_count)
        for end in range(start, bounded_end):
            token = tokens[end]
            compact_characters += len(token)
            if compact_characters > matcher.max_compact_characters:
                break
            compact += token
            if (
                compact_characters in matcher.exact_lengths
                and compact in matcher.exact_values
            ):
                return True
    return False


def _has_exact_private_atom(tokens: tuple[str, ...]) -> bool:
    return _has_exact_compact_window(tokens, _SENSITIVE_COMPACT_MATCHER)


def is_public_field_name(field: object) -> bool:
    name = unicodedata.normalize("NFKC", str(field or "")).strip()
    if not name or _CONTROL_CHARACTERS.search(name):
        return False
    if any(character in name for character in ("/", "\\", ":")):
        return False
    tokens = _semantic_tokens(name)
    if _has_exact_private_atom(tokens):
        return False
    if _has_exact_semantics(tokens, _CREDENTIAL_COMPACT_MATCHER):
        return False
    if any(
        token in _ALWAYS_PRIVATE_PATH_TOKENS
        or token.startswith(("directory", "dirname", "filepath"))
        for token in tokens
    ):
        return False
    if tokens == ("path",):
        return False
    return not _has_exact_semantics(tokens, _PHYSICAL_LOCATION_COMPACT_MATCHER)


def public_column_metadata(
    columns_info: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        item
        for item in columns_info
        if is_public_field_name(item.get("name"))
    ]
