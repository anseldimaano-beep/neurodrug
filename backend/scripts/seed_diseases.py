import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings
from app.db.base import Base
from app.models.domain import Disease

RARE_CANCERS = [
    {"name": "Glioblastoma", "efo_id": "EFO_0000519", "category": "brain_cancer", "description": "Most aggressive malignant primary brain tumor in adults."},
    {"name": "Neuroblastoma", "efo_id": "EFO_0000621", "category": "pediatric_cancer", "description": "Cancer formed from immature nerve cells, most common in infants."},
    {"name": "Medulloblastoma", "efo_id": "EFO_0002939", "category": "brain_cancer", "description": "Malignant pediatric brain tumor arising in the cerebellum."},
    {"name": "Ewing Sarcoma", "efo_id": "EFO_0000174", "category": "bone_cancer", "description": "Rare bone and soft tissue cancer in children and adolescents."},
    {"name": "Wilms Tumor", "efo_id": "EFO_0000642", "category": "kidney_cancer", "description": "Rare kidney cancer primarily affecting children."},
]


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    # FIX: use the real AsyncSession class, not a fake one built with type()
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        for cancer in RARE_CANCERS:
            d = Disease(**cancer)
            session.add(d)
        await session.commit()
        print(f"Seeded {len(RARE_CANCERS)} rare cancer diseases.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
