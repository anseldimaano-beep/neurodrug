from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_active_user
from app.models.domain import User
from app.services.ai_assistant import AIResearchAssistant

router = APIRouter()


@router.get("/explain/{prediction_id}")
async def explain_prediction(
    prediction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = AIResearchAssistant(db)
    return await service.explain_prediction(prediction_id)


@router.get("/summarize/{prediction_id}")
async def summarize_publications(
    prediction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = AIResearchAssistant(db)
    return await service.summarize_publications(prediction_id)
