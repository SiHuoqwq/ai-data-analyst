import pytest

from app.v2.services.structured_response import (
    StructuredResponseError,
    StructuredResponseParser,
)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"goal":"inspect","steps":[]}', {"goal": "inspect", "steps": []}),
        (
            '```json\n{"goal":"inspect","steps":[]}\n```',
            {"goal": "inspect", "steps": []},
        ),
        (
            '以下是计划：\n{"goal":"inspect","steps":[]}',
            {"goal": "inspect", "steps": []},
        ),
        (
            '{"goal":"inspect","steps":[]}\n请按此计划执行。',
            {"goal": "inspect", "steps": []},
        ),
    ],
)
def test_parser_extracts_one_complete_top_level_object(content, expected):
    assert StructuredResponseParser().parse_object(content) == expected


def test_parser_rejects_multiple_top_level_objects():
    with pytest.raises(StructuredResponseError):
        StructuredResponseParser().parse_object(
            '{"goal":"first","steps":[]} {"goal":"second","steps":[]}'
        )


def test_parser_does_not_execute_or_repair_non_json_text():
    with pytest.raises(StructuredResponseError):
        StructuredResponseParser().parse_object(
            "__import__('os').system('echo unsafe')"
        )
