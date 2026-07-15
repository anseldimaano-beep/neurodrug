from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, get_current_active_user
from app.models.domain import User, Prediction, Drug, Disease
from app.schemas.prediction import PredictionResponse, RepurposingRequest, RepurposingResponse
from app.services.repurposing import DrugRepurposingService
from app.services.ranking import PredictionRanker
from typing import List, Optional

router = APIRouter()


@router.get("/", response_model=List[PredictionResponse])
async def list_predictions(
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    disease_id: Optional[int] = None,
    disease_efo_id: Optional[str] = None,
    min_score: float = Query(default=0.0, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all drug repurposing predictions with optional filters."""
    query = select(Prediction).options(
        selectinload(Prediction.drug),
        selectinload(Prediction.disease),
    ).where(
        Prediction.is_deleted == False,
        Prediction.prediction_score >= min_score,
    )
    if disease_id:
        query = query.where(Prediction.disease_id == disease_id)
    elif disease_efo_id:
        disease_result = await db.execute(
            select(Disease).where(
                (Disease.efo_id == disease_efo_id) |
                (Disease.name.ilike(f"%{disease_efo_id}%"))
            )
        )
        disease = disease_result.scalar_one_or_none()
        if disease:
            query = query.where(Prediction.disease_id == disease.id)
    query = query.order_by(desc(Prediction.prediction_score)).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{prediction_id}", response_model=PredictionResponse)
async def get_prediction(
    prediction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Prediction)
        .options(selectinload(Prediction.drug), selectinload(Prediction.disease))
        .where(Prediction.id == prediction_id)
    )
    pred = result.scalar_one_or_none()
    if not pred:
        raise HTTPException(status_code=404, detail=f"Prediction {prediction_id} not found")
    return pred


@router.post("/run", response_model=RepurposingResponse, status_code=202)
async def run_repurposing(
    request: RepurposingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Run drug repurposing inference for a disease."""
    service = DrugRepurposingService(db)
    candidates = await service.run_inference(
        disease_efo_id=request.disease_efo_id,
        disease_mondo_id=request.disease_mondo_id,
        model_version_id=request.model_version_id,
        top_k=request.top_k,
    )
    ranked = PredictionRanker.rerank(candidates)
    return RepurposingResponse(
        disease=request.disease_efo_id,
        candidates=ranked,
        total=len(ranked),
        model_version_id=request.model_version_id,
    )