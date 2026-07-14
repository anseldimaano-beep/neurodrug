from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_active_user, require_role
from app.models.domain import User
from app.services.repurposing import DrugRepurposingService

router = APIRouter()


@router.post("/predict", status_code=status.HTTP_202_ACCEPTED)
async def run_prediction(
    disease_efo_id: str,
    model_version_id: int,
    top_k: int = 20,
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("researcher")),
):
    service = DrugRepurposingService(db)
    results = await service.run_inference(disease_efo_id, model_version_id, top_k)
    return {"disease": disease_efo_id, "candidates": results}
