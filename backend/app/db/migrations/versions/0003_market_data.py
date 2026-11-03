"""Persist Yahoo Finance quotes and daily bars."""

from alembic import op
import sqlalchemy as sa

revision = "0003_market_data"
down_revision = "0002_core_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_snapshots",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("close", sa.Float(), nullable=True),
        sa.Column("previous_close", sa.Float(), nullable=True),
        sa.Column("change_percent", sa.Float(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("market_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("instrument_id"),
    )
    op.create_table(
        "daily_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instrument_id", "trading_date", name="uq_daily_price_instrument_date"),
    )
    op.create_index("ix_daily_prices_instrument_id", "daily_prices", ["instrument_id"])


def downgrade() -> None:
    op.drop_index("ix_daily_prices_instrument_id", table_name="daily_prices")
    op.drop_table("daily_prices")
    op.drop_table("market_snapshots")
