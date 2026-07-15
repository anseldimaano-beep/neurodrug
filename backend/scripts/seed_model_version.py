import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select
from app.core.config import settings
from app.models.domain import ModelVersion

CHECKPOINT_PATH = "checkpoints/best_model.pt"

MODEL = {
    "name": "NeuroDrugHGT",
    "version": "1.0.0",
    "architecture": "HGT",
    "checkpoint_path": CHECKPOINT_PATH,
    "hyperparameters": {
        "hidden_channels": 128,
        "num_layers": 3,
        "num_heads": 4,
        "lr": 3e-4,
        "weight_decay": 1e-5,
        "max_epochs": 5,
    },
    "performance_metrics": {},
    "is_active": True,
    "is_production": True,
}


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.utcnow()

    async with Session() as session:
        # Check if a ModelVersion with this checkpoint already exists
        result = await session.execute(
            select(ModelVersion).where(ModelVersion.checkpoint_path == CHECKPOINT_PATH)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update in place
            existing.is_active = True
            existing.is_production = True
            existing.updated_at = now
            await session.commit()
            print(f"✅ ModelVersion already exists (id={existing.id}) — marked active/production.")
        else:
            mv = ModelVersion(
                **MODEL,
                created_at=now,
                updated_at=now,
                is_deleted=False,
            )
            session.add(mv)
            await session.commit()
            await session.refresh(mv)
            print(f"✅ ModelVersion seeded (id={mv.id}), checkpoint: {CHECKPOINT_PATH}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
