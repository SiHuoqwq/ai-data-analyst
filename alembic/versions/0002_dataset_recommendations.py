"""add cached dataset recommendations

Revision ID: 0002_dataset_recommendations
Revises: 0001_minimal_v2
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_dataset_recommendations"
down_revision = "0001_minimal_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_recommendations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "dataset_version_id",
            sa.String(),
            sa.ForeignKey("files.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("recommendations_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("provider_name", sa.String(), nullable=True),
        sa.Column("provider_model", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('model','template')",
            name="ck_dataset_recommendations_source",
        ),
    )


def downgrade() -> None:
    op.drop_table("dataset_recommendations")
