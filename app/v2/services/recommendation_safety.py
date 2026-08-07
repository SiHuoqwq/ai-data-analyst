import re
import unicodedata
from typing import Any, Iterable

from app.db.models import FileModel
from app.v2.schemas.recommendations import RecommendationCandidate


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_LOWER_TO_UPPER_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ACRONYM_BOUNDARY = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_SEMANTIC_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_ENGLISH_WORD = re.compile(r"[a-z0-9]+")
_CJK_SEQUENCE = re.compile(r"[\u3400-\u9fff]+")
_NATURAL_LANGUAGE_TEXT = re.compile(r"^[\w\s.,?!'’\-，。？！、]+$", re.UNICODE)
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
_NATURAL_GRAMMAR_WORDS = {
    "a",
    "across",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "has",
    "have",
    "how",
    "in",
    "is",
    "of",
    "on",
    "or",
    "per",
    "should",
    "the",
    "their",
    "these",
    "this",
    "to",
    "using",
    "what",
    "which",
    "with",
    "within",
}
_ANALYSIS_SUBJECT_WORDS = {
    "amount",
    "average",
    "categories",
    "category",
    "channel",
    "channels",
    "completion",
    "count",
    "course",
    "courses",
    "device",
    "devices",
    "difficulty",
    "dimension",
    "dimensions",
    "enrollment",
    "enrollments",
    "group",
    "groups",
    "level",
    "levels",
    "mean",
    "number",
    "outcome",
    "outcomes",
    "paid",
    "performance",
    "rate",
    "rates",
    "rating",
    "refund",
    "region",
    "regional",
    "regions",
    "result",
    "results",
    "revenue",
    "score",
    "scores",
    "segment",
    "segments",
    "total",
    "type",
    "types",
}
_ANALYSIS_QUALIFIER_WORDS = {
    "clearest",
    "different",
    "high",
    "higher",
    "highest",
    "key",
    "low",
    "lower",
    "lowest",
    "one",
    "opportunities",
    "opportunity",
    "safe",
    "strong",
    "stronger",
    "strongest",
    "two",
    "version",
    "weak",
    "weaker",
    "weakest",
}
_GROUP_ACTION_WORDS = {
    "analysis",
    "analyze",
    "compare",
    "compared",
    "comparison",
    "comparisons",
    "evaluate",
    "find",
    "identify",
    "rank",
    "show",
    "summarize",
    "use",
    "what",
    "which",
}
_MONTHLY_ACTION_WORDS = {
    "analysis",
    "analyze",
    "change",
    "changes",
    "compare",
    "decrease",
    "find",
    "fluctuation",
    "growth",
    "identify",
    "increase",
    "monthly",
    "show",
    "trend",
    "trends",
    "vary",
    "varies",
}
_MONTHLY_SUBJECT_WORDS = {"date", "dates", "month", "months", "period", "time"}
_CJK_GRAMMAR_PHRASES = {
    "中",
    "为",
    "了",
    "以及",
    "使用",
    "其中",
    "到",
    "和",
    "哪些",
    "哪类",
    "哪个",
    "在",
    "基于",
    "如何",
    "对",
    "将",
    "按",
    "是",
    "有什么",
    "有",
    "每",
    "用",
    "的",
    "与",
    "通过",
}
_CJK_ACTION_PHRASES = {
    "分析",
    "变化",
    "对比",
    "展示",
    "找出",
    "排名",
    "比较",
    "统计",
    "趋势",
    "识别",
}
_CJK_SUBJECT_PHRASES = {
    "不同",
    "人数",
    "低",
    "偏低",
    "偏高",
    "分类",
    "分组",
    "完成率",
    "实付金额",
    "平均",
    "总计",
    "报名人数",
    "数量",
    "月",
    "月份",
    "月度",
    "波动",
    "渠道",
    "类别",
    "结果",
    "评分",
    "课程",
    "较低",
    "较高",
    "退款率",
    "金额",
    "难度",
    "高",
}


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
    tokens: tuple[str, ...],
    qualifiers: set[str],
    nouns: set[str],
) -> bool:
    return any(
        token == qualifier + noun or token == noun + qualifier
        for token in tokens
        for qualifier in qualifiers
        for noun in nouns
    ) or any(
        (left in qualifiers and right in nouns)
        or (left in nouns and right in qualifiers)
        for left, right in zip(tokens, tokens[1:])
    )


def _has_exact_private_atom(tokens: tuple[str, ...]) -> bool:
    return any(token in _SENSITIVE_TOKENS for token in tokens) or any(
        left + right in _SENSITIVE_TOKENS
        for left, right in zip(tokens, tokens[1:])
    )


def is_public_field_name(field: object) -> bool:
    name = unicodedata.normalize("NFKC", str(field or "")).strip()
    if not name or _CONTROL_CHARACTERS.search(name):
        return False
    if any(character in name for character in ("/", "\\", ":")):
        return False
    tokens = _semantic_tokens(name)
    if _has_exact_private_atom(tokens):
        return False
    if _has_exact_semantics(
        tokens,
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
    if tokens == ("path",):
        return False
    return not _has_exact_semantics(
        tokens,
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


def _referenced_field_language(
    candidate: RecommendationCandidate,
) -> tuple[set[str], set[str]]:
    english_words: set[str] = set()
    cjk_phrases: set[str] = set()
    for field in candidate.referenced_fields:
        normalized = unicodedata.normalize("NFKC", field).casefold()
        english_words.update(_ENGLISH_WORD.findall(normalized))
        cjk_phrases.update(_CJK_SEQUENCE.findall(normalized))
    return english_words, cjk_phrases


def _contains_only_controlled_cjk(
    text: str,
    allowed_phrases: set[str],
) -> bool:
    phrases = tuple(sorted(allowed_phrases, key=len, reverse=True))
    for sequence in _CJK_SEQUENCE.findall(text):
        offset = 0
        while offset < len(sequence):
            match = next(
                (
                    phrase
                    for phrase in phrases
                    if sequence.startswith(phrase, offset)
                ),
                None,
            )
            if match is None:
                return False
            offset += len(match)
    return True


def _contains_allowed_analysis_language(
    candidate: RecommendationCandidate,
) -> bool:
    normalized_parts = tuple(
        unicodedata.normalize("NFKC", part).casefold()
        for part in (candidate.label, candidate.question)
    )
    if any(
        not _NATURAL_LANGUAGE_TEXT.fullmatch(part)
        for part in normalized_parts
    ):
        return False

    field_words, field_cjk = _referenced_field_language(candidate)
    action_words = (
        _MONTHLY_ACTION_WORDS
        if candidate.intent_type == "monthly_trend"
        else _GROUP_ACTION_WORDS
    )
    intent_subject_words = (
        _MONTHLY_SUBJECT_WORDS
        if candidate.intent_type == "monthly_trend"
        else set()
    )
    allowed_words = (
        _NATURAL_GRAMMAR_WORDS
        | _ANALYSIS_SUBJECT_WORDS
        | _ANALYSIS_QUALIFIER_WORDS
        | action_words
        | intent_subject_words
        | field_words
    )
    words = [
        word
        for part in normalized_parts
        for word in _ENGLISH_WORD.findall(part)
    ]
    if any(word not in allowed_words and not word.isdigit() for word in words):
        return False

    allowed_cjk = (
        _CJK_GRAMMAR_PHRASES
        | _CJK_ACTION_PHRASES
        | _CJK_SUBJECT_PHRASES
        | field_cjk
    )
    text = " ".join(normalized_parts)
    if not _contains_only_controlled_cjk(text, allowed_cjk):
        return False

    has_action = bool(action_words.intersection(words)) or any(
        phrase in text for phrase in _CJK_ACTION_PHRASES
    )
    has_subject = bool(
        (_ANALYSIS_SUBJECT_WORDS | intent_subject_words | field_words).intersection(
            words
        )
    ) or any(
        phrase in text for phrase in (_CJK_SUBJECT_PHRASES | field_cjk)
    )
    return has_action and has_subject


def contains_unsafe_recommendation_content(
    candidate: RecommendationCandidate,
    _file_record: FileModel,
) -> bool:
    parts = (candidate.label, candidate.question)
    if any(_CONTROL_CHARACTERS.search(part) for part in parts):
        return True
    return not _contains_allowed_analysis_language(candidate)
