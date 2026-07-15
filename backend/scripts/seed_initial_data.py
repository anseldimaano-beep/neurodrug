#!/usr/bin/env python3
"""Idempotent seed — safe to run multiple times."""
import sys, os
sys.path.insert(0, "/app")

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, text
from app.core.config import settings
from app.models.domain import Disease, Drug, Role, User, DataSource
from app.services.auth_service import AuthService
from datetime import datetime

RARE_CANCERS = [
    {"name": "Glioblastoma",   "efo_id": "MONDO_0018177", "category": "brain_cancer",    "description": "Most aggressive malignant primary brain tumor in adults."},
    {"name": "Neuroblastoma",  "efo_id": "MONDO_0005072", "category": "pediatric_cancer","description": "Cancer formed from immature nerve cells, most common in infants."},
    {"name": "Ewing Sarcoma",  "efo_id": "MONDO_0012817", "category": "bone_cancer",     "description": "Rare bone and soft tissue cancer in children and adolescents."},
    {"name": "Medulloblastoma","efo_id": "MONDO_0007959", "category": "brain_cancer",    "description": "Malignant pediatric brain tumor arising in the cerebellum."},
    {"name": "Wilms Tumor",    "efo_id": "MONDO_0019004", "category": "kidney_cancer",   "description": "Rare kidney cancer primarily affecting children."},
]

KNOWN_DRUGS = [
    {"name": "Temozolomide",   "chembl_id": "CHEMBL810",     "approval_status": "approved", "max_phase": 4, "mechanism_of_action": "DNA alkylating agent"},
    {"name": "Bevacizumab",    "chembl_id": "CHEMBL1201583", "approval_status": "approved", "max_phase": 4, "mechanism_of_action": "VEGF-A inhibitor"},
    {"name": "Imatinib",       "chembl_id": "CHEMBL941",     "approval_status": "approved", "max_phase": 4, "mechanism_of_action": "BCR-ABL tyrosine kinase inhibitor"},
    {"name": "Sunitinib",      "chembl_id": "CHEMBL535",     "approval_status": "approved", "max_phase": 4, "mechanism_of_action": "Multi-targeted RTK inhibitor"},
    {"name": "Erdafitinib",    "chembl_id": "CHEMBL3788023", "approval_status": "approved", "max_phase": 4, "mechanism_of_action": "FGFR inhibitor"},
    {"name": "Vincristine",    "chembl_id": "CHEMBL90555",   "approval_status": "approved", "max_phase": 4, "mechanism_of_action": "tubulin polymerization inhibitor"},
    {"name": "Dactinomycin",   "chembl_id": "CHEMBL1554",    "approval_status": "approved", "max_phase": 4, "mechanism_of_action": "DNA intercalation / topoisomerase II inhibition"},
    {"name": "Doxorubicin",    "chembl_id": "CHEMBL53463",   "approval_status": "approved", "max_phase": 4, "mechanism_of_action": "DNA intercalation / topoisomerase II inhibition"},
    {"name": "Cyclophosphamide","chembl_id": "CHEMBL88",     "approval_status": "approved", "max_phase": 4, "mechanism_of_action": "DNA alkylating agent"},
    {"name": "Etoposide",      "chembl_id": "CHEMBL44657",   "approval_status": "approved", "max_phase": 4, "mechanism_of_action": "topoisomerase II inhibitor"},
    {"name": "Carboplatin",    "chembl_id": "CHEMBL1351",    "approval_status": "approved", "max_phase": 4, "mechanism_of_action": "DNA cross-linking / platinum-based"},
    {"name": "Irinotecan",     "chembl_id": "CHEMBL481",     "approval_status": "approved", "max_phase": 4, "mechanism_of_action": "topoisomerase I inhibitor"},
    {"name": "Ifosfamide",     "chembl_id": "CHEMBL1024",    "approval_status": "approved", "max_phase": 4, "mechanism_of_action": "DNA alkylating agent"},
]

DATA_SOURCES = [
    {"name": "opentargets",    "url": "https://platform.opentargets.org",          "api_endpoint": settings.OPEN_TARGETS_API},
    {"name": "string",         "url": "https://string-db.org",                     "api_endpoint": settings.STRING_API},
    {"name": "dgidb",          "url": "https://dgidb.org",                         "api_endpoint": settings.DGIDB_API},
    {"name": "chembl",         "url": "https://www.ebi.ac.uk/chembl",              "api_endpoint": settings.CHEMBL_API},
    {"name": "clinicaltrials", "url": "https://clinicaltrials.gov",                "api_endpoint": settings.CLINICAL_TRIALS_API},
    {"name": "uniprot",        "url": "https://www.uniprot.org",                   "api_endpoint": settings.UNIPROT_API},
    {"name": "pubmed",         "url": "https://pubmed.ncbi.nlm.nih.gov",           "api_endpoint": settings.PUBMED_BASE_URL},
]


async def main():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.utcnow()

    async with Session() as db:

        # ── Roles (raw SQL so ON CONFLICT DO NOTHING works cleanly) ─────────
        await db.execute(text("""
            INSERT INTO roles (name, created_at, updated_at, version, is_deleted)
            VALUES
              ('admin',      :now, :now, 1, FALSE),
              ('researcher', :now, :now, 1, FALSE),
              ('viewer',     :now, :now, 1, FALSE)
            ON CONFLICT (name) DO NOTHING
        """), {"now": now})
        await db.flush()
        print("✓ roles")

        # ── Admin user ───────────────────────────────────────────────────────
        auth = AuthService(db)
        if not (await db.execute(
            select(User).where(User.email == "admin@neurodrug.local")
        )).scalar_one_or_none():
            db.add(User(
                email="admin@neurodrug.local",
                hashed_password=auth.get_password_hash("ChangeMe123!"),
                full_name="NeuroDrug Admin",
                is_superuser=True,
                is_active=True,
                created_at=now,
                updated_at=now,
            ))
            print("✓ admin user created")
        else:
            print("✓ admin user already exists")

        # ── Diseases ─────────────────────────────────────────────────────────
        added = 0
        for d in RARE_CANCERS:
            if not (await db.execute(
                select(Disease).where(Disease.name == d["name"])
            )).scalar_one_or_none():
                db.add(Disease(**d, created_at=now, updated_at=now))
                added += 1
        print(f"✓ diseases: {added} added, {len(RARE_CANCERS)-added} already existed")

        # ── Drugs ────────────────────────────────────────────────────────────
        added = 0
        for drug in KNOWN_DRUGS:
            if not (await db.execute(
                select(Drug).where(Drug.chembl_id == drug["chembl_id"])
            )).scalar_one_or_none():
                db.add(Drug(**drug, created_at=now, updated_at=now))
                added += 1
        print(f"✓ drugs: {added} added, {len(KNOWN_DRUGS)-added} already existed")

        # ── Data sources ─────────────────────────────────────────────────────
        added = 0
        for src in DATA_SOURCES:
            if not (await db.execute(
                select(DataSource).where(DataSource.name == src["name"])
            )).scalar_one_or_none():
                db.add(DataSource(**src, is_active=True, created_at=now, updated_at=now))
                added += 1
        print(f"✓ data_sources: {added} added, {len(DATA_SOURCES)-added} already existed")

        await db.commit()
        print("\n✅ Seed complete")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())