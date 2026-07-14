from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSON, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, AuditMixin


class User(Base, AuditMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role_id: Mapped[Optional[int]] = mapped_column(ForeignKey("roles.id"), nullable=True, index=True)

    role: Mapped[Optional["Role"]] = relationship("Role", back_populates="users")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="user")


class Role(Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    users: Mapped[List["User"]] = relationship("User", back_populates="role")
    permissions: Mapped[List["Permission"]] = relationship(
        "Permission", secondary="role_permissions", back_populates="roles"
    )


class Permission(Base):
    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)

    roles: Mapped[List["Role"]] = relationship(
        "Role", secondary="role_permissions", back_populates="permissions"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class Gene(Base, AuditMixin):
    __tablename__ = "genes"
    __table_args__ = (
        Index("ix_gene_symbol", "symbol"),
        Index("ix_gene_entrez", "entrez_id"),
    )

    symbol: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    entrez_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ensembl_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    chromosome: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    biotype: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_oncogene: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_tumor_suppressor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    proteins: Mapped[List["Protein"]] = relationship("Protein", back_populates="gene")
    interactions_as_source: Mapped[List["Interaction"]] = relationship(
        "Interaction", foreign_keys="Interaction.source_gene_id", back_populates="source_gene"
    )
    interactions_as_target: Mapped[List["Interaction"]] = relationship(
        "Interaction", foreign_keys="Interaction.target_gene_id", back_populates="target_gene"
    )


class Protein(Base, AuditMixin):
    __tablename__ = "proteins"

    uniprot_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    gene_id: Mapped[Optional[int]] = mapped_column(ForeignKey("genes.id"), nullable=True, index=True)
    sequence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    molecular_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    subcellular_location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    function: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    gene: Mapped[Optional["Gene"]] = relationship("Gene", back_populates="proteins")


class Drug(Base, AuditMixin):
    __tablename__ = "drugs"
    __table_args__ = (
        Index("ix_drug_chembl", "chembl_id"),
        Index("ix_drug_name", "name"),
    )

    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    chembl_id: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True)
    pubchem_cid: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    molecular_formula: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    molecular_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    smiles: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mechanism_of_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approval_status: Mapped[Optional[str]] = mapped_column(String(50), default="unknown", nullable=True)
    max_phase: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    first_approval_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    interactions: Mapped[List["Interaction"]] = relationship("Interaction", back_populates="drug")


class Disease(Base, AuditMixin):
    __tablename__ = "diseases"
    __table_args__ = (
        Index("ix_disease_efo", "efo_id"),
        Index("ix_disease_name", "name"),
    )

    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    efo_id: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True)
    mondo_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    icd10_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    prevalence: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    interactions: Mapped[List["Interaction"]] = relationship("Interaction", back_populates="disease")


class Interaction(Base, AuditMixin):
    __tablename__ = "interactions"
    __table_args__ = (
        Index("ix_interaction_type", "interaction_type"),
        Index("ix_interaction_confidence", "confidence_score"),
        UniqueConstraint(
            "source_gene_id", "target_gene_id", "interaction_type",
            "drug_id", "disease_id", name="uq_interaction"
        ),
    )

    interaction_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_gene_id: Mapped[Optional[int]] = mapped_column(ForeignKey("genes.id"), nullable=True, index=True)
    target_gene_id: Mapped[Optional[int]] = mapped_column(ForeignKey("genes.id"), nullable=True, index=True)
    drug_id: Mapped[Optional[int]] = mapped_column(ForeignKey("drugs.id"), nullable=True, index=True)
    disease_id: Mapped[Optional[int]] = mapped_column(ForeignKey("diseases.id"), nullable=True, index=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_database: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_directed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)

    source_gene: Mapped[Optional["Gene"]] = relationship(
        "Gene", foreign_keys=[source_gene_id], back_populates="interactions_as_source"
    )
    target_gene: Mapped[Optional["Gene"]] = relationship(
        "Gene", foreign_keys=[target_gene_id], back_populates="interactions_as_target"
    )
    drug: Mapped[Optional["Drug"]] = relationship("Drug", back_populates="interactions")
    disease: Mapped[Optional["Disease"]] = relationship("Disease", back_populates="interactions")


class KnowledgeGraphNode(Base, AuditMixin):
    __tablename__ = "knowledge_graph_nodes"
    __table_args__ = (
        Index("ix_kg_node_type", "node_type"),
        Index("ix_kg_node_external_id", "external_id"),
        UniqueConstraint("node_type", "external_id", name="uq_kg_node"),
    )

    node_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    features: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    embedding: Mapped[Optional[List[float]]] = mapped_column(ARRAY(Float), nullable=True)

    outgoing_edges: Mapped[List["KnowledgeGraphEdge"]] = relationship(
        "KnowledgeGraphEdge", foreign_keys="KnowledgeGraphEdge.source_node_id", back_populates="source_node"
    )
    incoming_edges: Mapped[List["KnowledgeGraphEdge"]] = relationship(
        "KnowledgeGraphEdge", foreign_keys="KnowledgeGraphEdge.target_node_id", back_populates="target_node"
    )


class KnowledgeGraphEdge(Base, AuditMixin):
    __tablename__ = "knowledge_graph_edges"
    __table_args__ = (
        Index("ix_kg_edge_type", "edge_type"),
        Index("ix_kg_edge_weight", "weight"),
    )

    edge_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_node_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_graph_nodes.id"), nullable=False, index=True
    )
    target_node_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_graph_nodes.id"), nullable=False, index=True
    )
    weight: Mapped[Optional[float]] = mapped_column(Float, default=1.0)
    properties: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)

    source_node: Mapped["KnowledgeGraphNode"] = relationship(
        "KnowledgeGraphNode", foreign_keys=[source_node_id], back_populates="outgoing_edges"
    )
    target_node: Mapped["KnowledgeGraphNode"] = relationship(
        "KnowledgeGraphNode", foreign_keys=[target_node_id], back_populates="incoming_edges"
    )


class Prediction(Base, AuditMixin):
    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_prediction_score", "prediction_score"),
        Index("ix_prediction_drug_disease", "drug_id", "disease_id"),
    )

    drug_id: Mapped[int] = mapped_column(ForeignKey("drugs.id"), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False, index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"), nullable=False)
    prediction_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    novelty_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_genes: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    affected_pathways: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)

    drug: Mapped["Drug"] = relationship("Drug")
    disease: Mapped["Disease"] = relationship("Disease")
    model_version: Mapped["ModelVersion"] = relationship("ModelVersion", back_populates="predictions")


class ClinicalEvidence(Base, AuditMixin):
    __tablename__ = "clinical_evidence"

    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), nullable=False, index=True)
    trial_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    trial_phase: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    recruitment_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    intervention: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    outcome_measure: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_level: Mapped[str] = mapped_column(String(50), default="level_3", nullable=False)
    supporting_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    prediction: Mapped["Prediction"] = relationship("Prediction")


class LiteratureEvidence(Base, AuditMixin):
    __tablename__ = "literature_evidence"

    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), nullable=False, index=True)
    pubmed_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    authors: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    journal: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    publication_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    evidence_level: Mapped[str] = mapped_column(String(50), default="level_3", nullable=False)
    supporting_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    prediction: Mapped["Prediction"] = relationship("Prediction")


class TrainingRun(Base, AuditMixin):
    __tablename__ = "training_runs"

    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    logs_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    model_version: Mapped["ModelVersion"] = relationship("ModelVersion", back_populates="training_runs")


class ModelVersion(Base, AuditMixin):
    __tablename__ = "model_versions"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    architecture: Mapped[str] = mapped_column(String(100), nullable=False)
    checkpoint_path: Mapped[str] = mapped_column(String(500), nullable=False)
    hyperparameters: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    performance_metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_production: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    predictions: Mapped[List["Prediction"]] = relationship("Prediction", back_populates="model_version")
    training_runs: Mapped[List["TrainingRun"]] = relationship("TrainingRun", back_populates="model_version")


class ApiLog(Base):
    __tablename__ = "api_logs"
    __table_args__ = (
        Index("ix_api_log_created_at", "created_at"),
        Index("ix_api_log_endpoint", "endpoint"),
    )

    method: Mapped[str] = mapped_column(String(10), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    client_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    request_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_created_at", "created_at"),
        Index("ix_audit_action", "action"),
    )

    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    old_values: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    new_values: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")


class DataSource(Base, AuditMixin):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_endpoint: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_fetch_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(50), default="never_run", nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ETLJob(Base):
    __tablename__ = "etl_jobs"

    source_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    records_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
