import pytest

from app.v2.services.field_requirements import (
    MissingRequiredFieldsError,
    RequiredFieldGuard,
)


LEARNING_COLUMNS = [
    {"name": "课程类别", "dtype": "object"},
    {"name": "课程难度", "dtype": "object"},
    {"name": "购买渠道", "dtype": "object"},
    {"name": "主要学习设备", "dtype": "object"},
    {"name": "课程完成率", "dtype": "float64"},
    {"name": "是否退款", "dtype": "bool"},
    {"name": "课程评分", "dtype": "float64"},
    {"name": "报名日期", "dtype": "datetime64[ns]"},
    {"name": "实付金额", "dtype": "float64"},
]


@pytest.mark.parametrize("teacher_term", ["教师", "老师", "讲师", "授课教师"])
def test_teacher_question_requires_a_teacher_related_column(teacher_term):
    question = f"请比较不同{teacher_term}的授课质量与课程完成率"

    with pytest.raises(MissingRequiredFieldsError) as raised:
        RequiredFieldGuard().validate(question, LEARNING_COLUMNS)

    assert raised.value.code == "MISSING_REQUIRED_FIELDS"
    assert raised.value.retryable is False
    assert "当前数据无法回答教师维度问题" in raised.value.message
    assert "教师姓名" in raised.value.message
    assert "教师ID" in raised.value.message
    assert "授课教师" in raised.value.message
    assert "教师评分" in raised.value.message


@pytest.mark.parametrize(
    "teacher_field",
    ["教师姓名", "教师ID", "教师 ID", "授课教师", "讲师", "教师评分"],
)
def test_teacher_question_is_allowed_when_a_teacher_field_exists(teacher_field):
    columns = [*LEARNING_COLUMNS, {"name": teacher_field, "dtype": "object"}]

    RequiredFieldGuard().validate(
        "分析不同教师的授课质量对课程完成率的影响",
        columns,
    )


@pytest.mark.parametrize(
    "question",
    [
        "比较不同课程类别的完成率和退款率",
        "按月份查看各课程类别的报名趋势",
    ],
)
def test_supported_questions_are_not_blocked_without_teacher_fields(question):
    RequiredFieldGuard().validate(question, LEARNING_COLUMNS)
