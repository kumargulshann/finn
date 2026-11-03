"""Add demo portfolio, announcements, metrics, and alert rules."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002_core_workflow"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table("portfolios", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False, unique=True), sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("portfolio_holdings", sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True), sa.Column("weight", sa.Float(), nullable=False, server_default="0"), sa.Column("price", sa.Float(), nullable=False, server_default="0"), sa.Column("daily_change", sa.Float(), nullable=False, server_default="0"), sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("announcements", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False), sa.Column("slug", sa.String(100), nullable=False, unique=True), sa.Column("category", sa.String(40), nullable=False), sa.Column("title", sa.String(300), nullable=False), sa.Column("summary", sa.Text(), nullable=False), sa.Column("why_it_matters", sa.Text(), nullable=False), sa.Column("severity", sa.String(20), nullable=False, server_default="Medium"), sa.Column("positive", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("published_at", sa.DateTime(timezone=True), nullable=False), sa.Column("source_name", sa.String(200), nullable=False), sa.Column("source_url", sa.String(500), nullable=False), sa.Column("source_date", sa.String(100), nullable=False), sa.Column("facts_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("is_saved", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_announcements_company_id", "announcements", ["company_id"])
    op.create_index("ix_announcements_slug", "announcements", ["slug"])
    op.create_table("financial_metrics", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False), sa.Column("metric", sa.String(80), nullable=False), sa.Column("value", sa.Float(), nullable=False), sa.Column("unit", sa.String(40), nullable=False), sa.Column("period", sa.String(40), nullable=False), sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index("ix_financial_metrics_company_id", "financial_metrics", ["company_id"])
    op.create_table("alert_rules", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False, unique=True), sa.Column("category", sa.String(40), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("threshold", sa.Float(), nullable=True))

def downgrade() -> None:
    op.drop_table("alert_rules")
    op.drop_index("ix_financial_metrics_company_id", table_name="financial_metrics")
    op.drop_table("financial_metrics")
    op.drop_index("ix_announcements_slug", table_name="announcements")
    op.drop_index("ix_announcements_company_id", table_name="announcements")
    op.drop_table("announcements")
    op.drop_table("portfolio_holdings")
    op.drop_table("portfolios")
