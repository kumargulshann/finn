"""Add exchange identities and stable announcement deduplication keys."""

from alembic import op
import sqlalchemy as sa

revision = "0004_announcements_pipeline"
down_revision = "0003_market_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("instruments", sa.Column("bse_scrip_code", sa.String(length=12), nullable=True))
    op.add_column("announcements", sa.Column("source_exchange", sa.String(length=8), nullable=False, server_default="DEMO"))
    op.add_column("announcements", sa.Column("source_key", sa.String(length=160), nullable=True))
    op.add_column("announcements", sa.Column("fingerprint", sa.String(length=64), nullable=True))
    op.create_index("ix_announcements_source_key", "announcements", ["source_key"], unique=True)
    op.create_index("ix_announcements_fingerprint", "announcements", ["fingerprint"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_announcements_fingerprint", table_name="announcements")
    op.drop_index("ix_announcements_source_key", table_name="announcements")
    op.drop_column("announcements", "fingerprint")
    op.drop_column("announcements", "source_key")
    op.drop_column("announcements", "source_exchange")
    op.drop_column("instruments", "bse_scrip_code")
