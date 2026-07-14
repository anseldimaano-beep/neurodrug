# C9b PATCH — apply to backend/app/models/domain.py
#
# PROBLEM: ApiLog and AuditLog both declare Index(..., "timestamp") but
# neither model defines a `timestamp` column.  Base provides `created_at`
# and `updated_at`.  SQLAlchemy 2.0 raises:
#
#   ArgumentError: Column 'timestamp' is not a column or
#   mapper-level relationship of mapper[ApiLog(api_logs)]
#
# during mapper configuration, which prevents the entire ORM from
# initialising (all imports of domain.py fail).
#
# FIX: change "timestamp" → "created_at" in both index definitions.
#
# Replace this block in domain.py:
# ─────────────────────────────────────────────────────────────────────
# class ApiLog(Base):
#     __tablename__ = "api_logs"
#     __table_args__ = (
#         Index("ix_api_log_timestamp", "timestamp"),    ← broken
#         Index("ix_api_log_endpoint", "endpoint"),
#     )
#
# Replace with:
# ─────────────────────────────────────────────────────────────────────
class ApiLog(Base):
    __tablename__ = "api_logs"
    __table_args__ = (
        Index("ix_api_log_created_at", "created_at"),   # FIX C9b
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


# ─────────────────────────────────────────────────────────────────────
# Replace this block in domain.py:
#
# class AuditLog(Base):
#     __tablename__ = "audit_logs"
#     __table_args__ = (
#         Index("ix_audit_timestamp", "timestamp"),      ← broken
#         Index("ix_audit_action", "action"),
#     )
#
# Replace with:
# ─────────────────────────────────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_created_at", "created_at"),     # FIX C9b
        Index("ix_audit_action", "action"),
    )

    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    old_values: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    new_values: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")
