"""Create the initial company and instrument tables."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sector", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_companies_name", "companies", ["name"], unique=True)
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("exchange", sa.String(length=8), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("provider_symbol", sa.String(length=48), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("exchange", "symbol", name="uq_instrument_exchange_symbol"),
    )
    op.create_index("ix_instruments_symbol", "instruments", ["symbol"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_instruments_symbol", table_name="instruments")
    op.drop_table("instruments")
    op.drop_index("ix_companies_name", table_name="companies")
    op.drop_table("companies")
