import pytest

from app.v2.services.field_requirements import (
    MissingRequiredFieldsError,
    RequiredFieldGuard,
)


REAL_ESTATE_COLUMNS = [
    {"name": "城市", "dtype": "object"},
    {"name": "区域", "dtype": "object"},
    {"name": "获客渠道", "dtype": "object"},
    {"name": "客户等级", "dtype": "object"},
    {"name": "成交金额", "dtype": "float64"},
    {"name": "回款金额", "dtype": "float64"},
    {"name": "签约日期", "dtype": "datetime64[ns]"},
]


@pytest.mark.parametrize("consultant_term", ["置业顾问", "销售顾问", "顾问"])
def test_sales_consultant_question_requires_a_consultant_column(consultant_term):
    question = f"请比较不同{consultant_term}的成交套数和成交金额"

    with pytest.raises(MissingRequiredFieldsError) as raised:
        RequiredFieldGuard().validate(question, REAL_ESTATE_COLUMNS)

    assert raised.value.code == "MISSING_REQUIRED_FIELDS"
    assert raised.value.retryable is False
    assert "当前数据中缺少「置业顾问」字段" in raised.value.message
    assert "置业顾问维度分析" in raised.value.message
    assert raised.value.details["concept"] == "sales_consultant"


@pytest.mark.parametrize("project_term", ["项目", "楼盘"])
def test_project_question_requires_a_project_column(project_term):
    question = f"哪个{project_term}成交金额最高？"

    with pytest.raises(MissingRequiredFieldsError) as raised:
        RequiredFieldGuard().validate(question, REAL_ESTATE_COLUMNS)

    assert raised.value.code == "MISSING_REQUIRED_FIELDS"
    assert "当前数据中缺少「项目」字段" in raised.value.message
    assert raised.value.details["concept"] == "project_name"


@pytest.mark.parametrize("channel_term", ["渠道", "获客渠道", "客户来源", "线索来源"])
def test_channel_question_requires_a_channel_column_when_missing(channel_term):
    columns = [
        {"name": "城市", "dtype": "object"},
        {"name": "成交金额", "dtype": "float64"},
    ]
    question = f"各{channel_term}成交表现怎么样？"

    with pytest.raises(MissingRequiredFieldsError) as raised:
        RequiredFieldGuard().validate(question, columns)

    assert raised.value.code == "MISSING_REQUIRED_FIELDS"
    assert "当前数据中缺少「获客渠道」字段" in raised.value.message
    assert raised.value.details["concept"] == "lead_channel"


@pytest.mark.parametrize("property_term", ["户型", "房型"])
def test_property_type_question_requires_a_property_type_column(property_term):
    question = f"比较不同{property_term}的成交表现"

    with pytest.raises(MissingRequiredFieldsError) as raised:
        RequiredFieldGuard().validate(question, REAL_ESTATE_COLUMNS)

    assert raised.value.code == "MISSING_REQUIRED_FIELDS"
    assert "当前数据中缺少「户型」字段" in raised.value.message
    assert raised.value.details["concept"] == "property_type"


@pytest.mark.parametrize(
    "consultant_field",
    ["置业顾问", "销售顾问", "置业顾问姓名"],
)
def test_sales_consultant_question_is_allowed_when_a_consultant_field_exists(
    consultant_field,
):
    columns = [*REAL_ESTATE_COLUMNS, {"name": consultant_field, "dtype": "object"}]

    RequiredFieldGuard().validate(
        "分析各置业顾问的成交套数排名",
        columns,
    )


@pytest.mark.parametrize(
    "question",
    [
        "各获客渠道的成交套数和成交金额怎么样？",
        "最近几个月成交金额趋势如何？",
        "不同客户等级的成交表现有何差异？",
    ],
)
def test_supported_questions_are_not_blocked_with_available_dimensions(question):
    RequiredFieldGuard().validate(question, REAL_ESTATE_COLUMNS)


def test_unsupported_teacher_question_is_not_a_field_guard_blocker():
    # 教育语义不再是领域守卫的一部分，应直接放行由意图路由拒绝。
    RequiredFieldGuard().validate(
        "不同老师的课程完成率怎么样？",
        REAL_ESTATE_COLUMNS,
    )
