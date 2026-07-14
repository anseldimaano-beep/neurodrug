from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_active_user
from app.models.domain import User
from app.services.validation.literature import LiteratureValidationService
from app.services.validation.clinical import ClinicalValidationService
from app.services.validation.biological import BiologicalValidationService

router = APIRouter()


# ------------------------------------------------------------------ #
# FIX C4: The frontend calls POST /validation/run with               #
# {"prediction_id": <int>}.  No such endpoint existed; every click   #
# returned 404.  This endpoint orchestrates all three validators in  #
# parallel and returns a combined evidence summary.                   #
# ------------------------------------------------------------------ #

class ValidationRequest(BaseModel):
    prediction_id: int


@router.post("/run")
async def run_validation(
    request: ValidationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Orchestrate literature, clinical, and biological validation for a
    prediction in a single call.  Returns a combined evidence summary.
    """
    prediction_id = request.prediction_id

    lit_service = LiteratureValidationService(db)
    clin_service = ClinicalValidationService(db)
    bio_service = BiologicalValidationService(db)

    literature_evidences = await lit_service.validate_prediction(prediction_id)
    clinical_evidences = await clin_service.validate_prediction(prediction_id)
    biological_result = await bio_service.validate_prediction(prediction_id)

    return {
        "prediction_id": prediction_id,
        "literature": {
            "evidence_count": len(literature_evidences),
        },
        "clinical": {
            "trial_count": len(clinical_evidences),
        },
        "biological": biological_result,
        "total_evidence_count": (
            len(literature_evidences) + len(clinical_evidences)
        ),
    }


# Individual sub-validators remain available for granular calls

@router.post("/{prediction_id}/literature")
async def validate_literature(
    prediction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = LiteratureValidationService(db)
    evidences = await service.validate_prediction(prediction_id)
    return {"prediction_id": prediction_id, "evidence_count": len(evidences)}


@router.post("/{prediction_id}/clinical")
async def validate_clinical(
    prediction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ClinicalValidationService(db)
    evidences = await service.validate_prediction(prediction_id)
    return {"prediction_id": prediction_id, "trial_count": len(evidences)}


@router.post("/{prediction_id}/biological")
async def validate_biological(
    prediction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = BiologicalValidationService(db)
    result = await service.validate_prediction(prediction_id)
    return result
