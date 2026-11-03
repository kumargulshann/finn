"""Persist indexed company reports and transcript passages."""

from alembic import op
import sqlalchemy as sa

revision = "0005_research_documents"
down_revision = "0004_announcements_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=220), nullable=False),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("fiscal_period", sa.String(length=40), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "source_key", name="uq_research_document_company_source"),
    )
    op.create_index("ix_research_documents_company_id", "research_documents", ["company_id"])
    op.create_index("ix_research_documents_document_type", "research_documents", ["document_type"])
    op.create_table(
        "research_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("financial_metrics_json", sa.Text(), nullable=False),
        sa.Column("guidance_json", sa.Text(), nullable=False),
        sa.Column("business_updates_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["research_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "page_number", "chunk_index", name="uq_research_chunk_page_index"),
    )
    op.create_index("ix_research_chunks_document_id", "research_chunks", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_research_chunks_document_id", table_name="research_chunks")
    op.drop_table("research_chunks")
    op.drop_index("ix_research_documents_document_type", table_name="research_documents")
    op.drop_index("ix_research_documents_company_id", table_name="research_documents")
    op.drop_table("research_documents")
