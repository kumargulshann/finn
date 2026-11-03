"""Store structured enrichment extracted from filings (results table, people profiles, EOD trigger metrics)."""

from alembic import op
import sqlalchemy as sa

revision = "0006_announcement_enrichment"
down_revision = "0005_research_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("announcements") as batch:
        batch.add_column(sa.Column("enrichment_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("announcements") as batch:
        batch.drop_column("enrichment_json")
