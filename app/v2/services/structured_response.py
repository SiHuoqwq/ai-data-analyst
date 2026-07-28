import json
import re
from typing import Any


class StructuredResponseError(ValueError):
    pass


class StructuredResponseParser:
    _fence_line = re.compile(r"(?m)^\s*```(?:json)?\s*$", re.IGNORECASE)

    def parse_object(self, content: str) -> dict[str, Any]:
        normalized = self._fence_line.sub("", content.strip()).strip()
        candidates = self._top_level_objects(normalized)
        parsed: list[dict[str, Any]] = []
        for candidate in candidates:
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                parsed.append(value)
        if len(parsed) != 1:
            raise StructuredResponseError(
                "response must contain exactly one JSON object"
            )
        return parsed[0]

    @staticmethod
    def _top_level_objects(content: str) -> list[str]:
        result: list[str] = []
        start: int | None = None
        depth = 0
        in_string = False
        escaped = False
        for index, character in enumerate(content):
            if start is None:
                if character == "{":
                    start = index
                    depth = 1
                    in_string = False
                    escaped = False
                continue
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
                continue
            if character == '"':
                in_string = True
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    result.append(content[start : index + 1])
                    start = None
        return result
