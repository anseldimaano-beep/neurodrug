"""Initial schema — all NeuroDrug v4 tables

Revision ID: 001
Revises: 
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # roles
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(100), unique=True, index=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1, nullable=False),
        sa.Column("is_deleted", sa.Boolean(), default=False, nullable=False, index=True),
    )
    # permissions
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("resource", sa.String(100), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
    )
    # role_permissions
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.Integer(), sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("id", sa.Integer(), primary_key=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
    )
    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("email", sa.String(255), unique=True, index=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("is_superuser", sa.Boolean(), default=False, nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1, nullable=False),
        sa.Column("is_deleted", sa.Boolean(), default=False, nullable=False, index=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    # genes
    op.create_table(
        "genes",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("symbol", sa.String(50), unique=True, index=True, nullable=False),
        sa.Column("entrez_id", sa.String(50), nullable=True),
        sa.Column("ensembl_id", sa.String(50), nullable=True),
        sa.Column("name", sa.String(500), nullable=True),
        sa.Column("chromosome", sa.String(20), nullable=True),
        sa.Column("biotype", sa.String(50), nullable=True),
        sa.Column("is_oncogene", sa.Boolean(), default=False, nullable=False),
        sa.Column("is_tumor_suppressor", sa.Boolean(), default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False, index=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_gene_symbol", "genes", ["symbol"])
    op.create_index("ix_gene_entrez", "genes", ["entrez_id"])

    # proteins
    op.create_table(
        "proteins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uniprot_id", sa.String(50), unique=True, index=True, nullable=False),
        sa.Column("gene_id", sa.Integer(), sa.ForeignKey("genes.id"), nullable=True, index=True),
        sa.Column("sequence", sa.Text(), nullable=True),
        sa.Column("length", sa.Integer(), nullable=True),
        sa.Column("molecular_weight", sa.Float(), nullable=True),
        sa.Column("subcellular_location", sa.Text(), nullable=True),
        sa.Column("function", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )

    # drugs
    op.create_table(
        "drugs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), index=True, nullable=False),
        sa.Column("chembl_id", sa.String(50), unique=True, nullable=True),
        sa.Column("pubchem_cid", sa.String(50), nullable=True),
        sa.Column("molecular_formula", sa.String(200), nullable=True),
        sa.Column("molecular_weight", sa.Float(), nullable=True),
        sa.Column("smiles", sa.Text(), nullable=True),
        sa.Column("mechanism_of_action", sa.Text(), nullable=True),
        sa.Column("approval_status", sa.String(50), default="unknown"),
        sa.Column("max_phase", sa.Integer(), nullable=True),
        sa.Column("first_approval_year", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_drug_chembl", "drugs", ["chembl_id"])
    op.create_index("ix_drug_name", "drugs", ["name"])

    # diseases
    op.create_table(
        "diseases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), index=True, nullable=False),
        sa.Column("efo_id", sa.String(50), unique=True, nullable=True),
        sa.Column("mondo_id", sa.String(50), nullable=True),
        sa.Column("icd10_code", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("prevalence", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_disease_efo", "diseases", ["efo_id"])
    op.create_index("ix_disease_name", "diseases", ["name"])

    # interactions
    op.create_table(
        "interactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("interaction_type", sa.String(50), nullable=False, index=True),
        sa.Column("source_gene_id", sa.Integer(), sa.ForeignKey("genes.id"), nullable=True, index=True),
        sa.Column("target_gene_id", sa.Integer(), sa.ForeignKey("genes.id"), nullable=True, index=True),
        sa.Column("drug_id", sa.Integer(), sa.ForeignKey("drugs.id"), nullable=True, index=True),
        sa.Column("disease_id", sa.Integer(), sa.ForeignKey("diseases.id"), nullable=True, index=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("evidence_score", sa.Float(), nullable=True),
        sa.Column("source_database", sa.String(100), nullable=False),
        sa.Column("evidence_type", sa.String(100), nullable=True),
        sa.Column("is_directed", sa.Boolean(), default=True),
        sa.Column("extra_metadata", postgresql.JSON(astext_type=sa.Text()), default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint(
            "source_gene_id", "target_gene_id", "interaction_type", "drug_id", "disease_id",
            name="uq_interaction"
        ),
    )
    op.create_index("ix_interaction_type", "interactions", ["interaction_type"])
    op.create_index("ix_interaction_confidence", "interactions", ["confidence_score"])

    # model_versions
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("architecture", sa.String(100), nullable=False),
        sa.Column("checkpoint_path", sa.String(500), nullable=False),
        sa.Column("hyperparameters", postgresql.JSON(astext_type=sa.Text()), default=dict),
        sa.Column("performance_metrics", postgresql.JSON(astext_type=sa.Text()), default=dict),
        sa.Column("is_active", sa.Boolean(), default=False),
        sa.Column("is_production", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )

    # predictions
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("drug_id", sa.Integer(), sa.ForeignKey("drugs.id"), nullable=False, index=True),
        sa.Column("disease_id", sa.Integer(), sa.ForeignKey("diseases.id"), nullable=False, index=True),
        sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("model_versions.id"), nullable=False),
        sa.Column("prediction_score", sa.Float(), nullable=False, index=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("novelty_score", sa.Float(), nullable=True),
        sa.Column("evidence_score", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("target_genes", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("affected_pathways", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("status", sa.String(50), default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_prediction_score", "predictions", ["prediction_score"])
    op.create_index("ix_prediction_drug_disease", "predictions", ["drug_id", "disease_id"])

    # training_runs
    op.create_table(
        "training_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("model_versions.id"), nullable=False, index=True),
        sa.Column("status", sa.String(50), default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config", postgresql.JSON(astext_type=sa.Text()), default=dict),
        sa.Column("metrics", postgresql.JSON(astext_type=sa.Text()), default=dict),
        sa.Column("logs_path", sa.String(500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )

    # knowledge_graph_nodes
    op.create_table(
        "knowledge_graph_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("node_type", sa.String(50), nullable=False, index=True),
        sa.Column("external_id", sa.String(100), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("features", postgresql.JSON(astext_type=sa.Text()), default=dict),
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("node_type", "external_id", name="uq_kg_node"),
    )

    # knowledge_graph_edges
    op.create_table(
        "knowledge_graph_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edge_type", sa.String(50), nullable=False, index=True),
        sa.Column("source_node_id", sa.Integer(), sa.ForeignKey("knowledge_graph_nodes.id"), nullable=False, index=True),
        sa.Column("target_node_id", sa.Integer(), sa.ForeignKey("knowledge_graph_nodes.id"), nullable=False, index=True),
        sa.Column("weight", sa.Float(), default=1.0),
        sa.Column("properties", postgresql.JSON(astext_type=sa.Text()), default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )

    # clinical_evidence
    op.create_table(
        "clinical_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id"), nullable=False, index=True),
        sa.Column("trial_id", sa.String(100), nullable=False, index=True),
        sa.Column("trial_phase", sa.String(50), nullable=True),
        sa.Column("recruitment_status", sa.String(50), nullable=True),
        sa.Column("intervention", sa.String(500), nullable=True),
        sa.Column("outcome_measure", sa.Text(), nullable=True),
        sa.Column("evidence_level", sa.String(50), default="level_3"),
        sa.Column("supporting_text", sa.Text(), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )

    # literature_evidence
    op.create_table(
        "literature_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id"), nullable=False, index=True),
        sa.Column("pubmed_id", sa.String(50), nullable=False, index=True),
        sa.Column("title", sa.String(1000), nullable=True),
        sa.Column("authors", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("journal", sa.String(500), nullable=True),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("evidence_level", sa.String(50), default="level_3"),
        sa.Column("supporting_text", sa.Text(), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )

    # data_sources
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("api_endpoint", sa.String(500), nullable=True),
        sa.Column("last_fetch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(50), default="never_run"),
        sa.Column("record_count", sa.Integer(), default=0),
        sa.Column("error_count", sa.Integer(), default=0),
        sa.Column("extra_metadata", postgresql.JSON(astext_type=sa.Text()), default=dict),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )

    # etl_jobs
    op.create_table(
        "etl_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(100), nullable=False, index=True),
        sa.Column("status", sa.String(50), default="pending"),
        sa.Column("records_processed", sa.Integer(), default=0),
        sa.Column("records_inserted", sa.Integer(), default=0),
        sa.Column("records_failed", sa.Integer(), default=0),
        sa.Column("error_log", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(100), nullable=False, index=True),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("old_values", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("new_values", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
    )

    # api_logs
    op.create_table(
        "api_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_time_ms", sa.Float(), nullable=False),
        sa.Column("client_ip", sa.String(50), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("request_body", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_deleted", sa.Boolean(), default=False),
    )
    op.create_index("ix_api_log_timestamp", "api_logs", ["created_at"])
    op.create_index("ix_api_log_endpoint", "api_logs", ["endpoint"])


def downgrade() -> None:
    for table in [
        "api_logs", "audit_logs", "etl_jobs", "data_sources",
        "literature_evidence", "clinical_evidence",
        "knowledge_graph_edges", "knowledge_graph_nodes",
        "training_runs", "predictions", "model_versions",
        "interactions", "diseases", "drugs", "proteins", "genes",
        "users", "role_permissions", "permissions", "roles",
    ]:
        op.drop_table(table)
