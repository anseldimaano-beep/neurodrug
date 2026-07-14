#!/usr/bin/env python3
"""Seed initial database with known cancer diseases and approved drugs."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.models.domain import Disease, Drug, Role, Permission, User, DataSource
from app.services.auth_service import AuthService
from datetime import datetime


RARE_CANCERS = [
    {"name": "Glioblastoma Multiforme", "efo_id": "EFO_0000519", "category": "rare_cancer"},
    {"name": "Neuroblastoma", "efo_id": "EFO_0000621", "category": "rare_cancer"},
    {"name": "Ewing Sarcoma", "efo_id": "EFO_0000400", "category": "rare_cancer"},
    {"name": "Medulloblastoma", "efo_id": "EFO_0002559", "category": "rare_cancer"},
    {"name": "Diffuse Intrinsic Pontine Glioma", "efo_id": "EFO_0003165", "category": "rare_cancer"},
]

KNOWN_DRUGS = [
    {"name": "Temozolomide", "chembl_id": "CHEMBL614", "approval_status": "approved", "max_phase": 4},
    {"name": "Bevacizumab", "chembl_id": "CHEMBL1201583", "approval_status": "approved", "max_phase": 4},
    {"name": "Imatinib", "chembl_id": "CHEMBL941", "approval_status": "approved", "max_phase": 4},
    {"name": "Sunitinib", "chembl_id": "CHEMBL535", "approval_status": "approved", "max_phase": 4},
    {"name": "Erdafitinib", "chembl_id": "CHEMBL3788023", "approval_status": "approved", "max_phase": 4},
]

DATA_SOURCES = [
    {"name": "opentargets", "url": "https://platform.opentargets.org", "api_endpoint": settings.OPEN_TARGETS_API},
    {"name": "string", "url": "https://string-db.org", "api_endpoint": settings.STRING_API},
    {"name": "dgidb", "url": "https://dgidb.org", "api_endpoint": settings.DGIDB_API},
    {"name": "chembl", "url": "https://www.ebi.ac.uk/chembl", "api_endpoint": settings.CHEMBL_API},
    {"name": "clinicaltrials", "url": "https://clinicaltrials.gov", "api_endpoint": settings.CLINICAL_TRIALS_API},
    {"name": "uniprot", "url": "https://www.uniprot.org", "api_endpoint": settings.UNIPROT_API},
    {"name": "pubmed", "url": "https://pubmed.ncbi.nlm.nih.gov", "api_endpoint": settings.PUBMED_BASE_URL},
]


async def main():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as db:
        now = datetime.utcnow()

        # Roles
        for role_name in ["admin", "researcher", "viewer"]:
            role = Role(name=role_name, created_at=now, updated_at=now)
            db.add(role)
        await db.flush()

        # Admin user
        auth = AuthService(db)
        admin = User(
            email="admin@neurodrug.local",
            hashed_password=auth.get_password_hash("ChangeMe123!"),
            full_name="NeuroDrug Admin",
            is_superuser=True,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(admin)

        # Diseases
        for d in RARE_CANCERS:
            db.add(Disease(**d, created_at=now, updated_at=now))

        # Drugs
        for drug in KNOWN_DRUGS:
            db.add(Drug(**drug, created_at=now, updated_at=now))

        # Data sources
        for src in DATA_SOURCES:
            db.add(DataSource(**src, is_active=True, created_at=now, updated_at=now))

        await db.commit()
        print("✅ Initial data seeded successfully")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
