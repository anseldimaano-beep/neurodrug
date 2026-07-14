from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_active_user
from app.models.domain import User
from app.services.reporting import ScientificReportingService

router = APIRouter()


@router.get("/predictions/csv")
async def export_predictions_csv(
    disease_efo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ScientificReportingService(db)
    csv_data = await service.generate_prediction_csv(disease_efo_id)
    return PlainTextResponse(content=csv_data, media_type="text/csv")


@router.get("/predictions/summary")
async def prediction_summary(
    disease_efo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ScientificReportingService(db)
    return await service.generate_summary_json(disease_efo_id)
