import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.dialects.postgresql import insert
from app.core.config import settings
from app.models.domain import Disease

RARE_CANCERS = [
    {"name": "Glioblastoma", "efo_id": "MONDO_0018177", "category": "brain_cancer",
     "description": "Most aggressive malignant primary brain tumor in adults."},
    {"name": "Neuroblastoma", "efo_id": "MONDO_0005072", "category": "pediatric_cancer",
     "description": "Cancer formed from immature nerve cells, most common in infants."},
    {"name": "Medulloblastoma", "efo_id": "MONDO_0007959", "category": "brain_cancer",
     "description": "Malignant pediatric brain tumor arising in the cerebellum."},
    {"name": "Ewing Sarcoma", "efo_id": "MONDO_0012817", "category": "bone_cancer",
     "description": "Rare bone and soft tissue cancer in children and adolescents."},
    {"name": "Wilms Tumor", "efo_id": "MONDO_0019004", "category": "kidney_cancer",
     "description": "Rare kidney cancer primarily affecting children."},
]


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.utcnow()

    async with Session() as session:
        for cancer in RARE_CANCERS:
            stmt = (
                insert(Disease)
                .values(
                    name=cancer["name"],
                    efo_id=cancer["efo_id"],
                    category=cancer["category"],
                    description=cancer["description"],
                    version=1,
                    is_deleted=False,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["efo_id"],
                    set_={
                        "name": cancer["name"],
                        "category": cancer["category"],
                        "description": cancer["description"],
                        "updated_at": now,
                    },
                )
            )
            await session.execute(stmt)

        await session.commit()
        print(f"✅ Upserted {len(RARE_CANCERS)} rare cancer diseases.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
