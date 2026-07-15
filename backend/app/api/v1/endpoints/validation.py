from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api.deps import get_db, get_current_active_user
from app.models.domain import User, Prediction, LiteratureEvidence, ClinicalEvidence
from app.services.validation.literature import LiteratureValidationService
from app.services.validation.clinical import ClinicalValidationService
from app.services.validation.biological import BiologicalValidationService
from app.core.logging import logger
from typing import List

router = APIRouter()


def _shape_evidence(
    prediction_id: int,
    literature_evidences: list,
    clinical_evidences: list,
    biological_result: dict,
    errors: dict | None = None,
) -> dict:
    """Shared response shaping for /run and /bulk so both return an
    identical structure — the frontend doesn't need to know whether a
    result came from a live validation or a DB read."""
    literature_items = [
        {
            "pubmed_id": ev.pubmed_id,
            "title": ev.title,
            "journal": ev.journal,
            "year": ev.publication_year,
            "url": ev.url,
        }
        for ev in literature_evidences
    ]
    clinical_items = [
        {
            "trial_id": ev.trial_id,
            "phase": ev.trial_phase,
            "status": ev.recruitment_status,
            "url": ev.url,
        }
        for ev in clinical_evidences
    ]
    target_gene_links = [
        {"gene": g, "url": f"https://www.genecards.org/cgi-bin/carddisp.pl?gene={g}"}
        for g in biological_result.get("target_genes", [])
    ]
    disease_gene_links = [
        {"gene": g, "url": f"https://www.genecards.org/cgi-bin/carddisp.pl?gene={g}"}
        for g in biological_result.get("disease_genes", [])
    ]

    return {
        "prediction_id": prediction_id,
        "literature": {
            "evidence_count": len(literature_evidences),
            "items": literature_items,
        },
        "clinical": {
            "trial_count": len(clinical_evidences),
            "items": clinical_items,
        },
        "biological": {
            **biological_result,
            "target_gene_links": target_gene_links,
            "disease_gene_links": disease_gene_links,
        },
        "total_evidence_count": (
            len(literature_evidences) + len(clinical_evidences)
        ),
        "errors": errors or {},
    }


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
    prediction in a single call — hits PubMed/ClinicalTrials.gov live
    and writes fresh rows to the DB. Returns a combined evidence summary.
    """
    prediction_id = request.prediction_id

    lit_service = LiteratureValidationService(db)
    clin_service = ClinicalValidationService(db)
    bio_service = BiologicalValidationService(db)

    # FIX C8: previously these three ran with plain `await` — if any one
    # raised (e.g. NCBI/ClinicalTrials.gov rate-limiting mid-"Validate All"),
    # the whole /run request 500'd and the frontend silently discarded
    # everything, including evidence the other two services *did* find.
    # Run independently and report which (if any) failed instead.
    errors: dict[str, str] = {}

    try:
        literature_evidences = await lit_service.validate_prediction(prediction_id)
    except Exception as exc:
        logger.warning(f"Literature validation failed for prediction {prediction_id}: {exc}")
        literature_evidences = []
        errors["literature"] = str(exc)

    try:
        clinical_evidences = await clin_service.validate_prediction(prediction_id)
    except Exception as exc:
        logger.warning(f"Clinical validation failed for prediction {prediction_id}: {exc}")
        clinical_evidences = []
        errors["clinical"] = str(exc)

    try:
        biological_result = await bio_service.validate_prediction(prediction_id)
    except Exception as exc:
        logger.warning(f"Biological validation failed for prediction {prediction_id}: {exc}")
        biological_result = {}
        errors["biological"] = str(exc)

    return _shape_evidence(
        prediction_id, literature_evidences, clinical_evidences, biological_result, errors
    )


# ------------------------------------------------------------------ #
# FIX C9: literature/clinical evidence is already persisted in the   #
# DB by /run. Previously the ONLY way to see it again was to click   #
# "Validate" again, which re-hit PubMed/ClinicalTrials.gov (rate-    #
# limit risk) and threw away everything as soon as the component     #
# unmounted (switching tabs, switching disease and back). This       #
# endpoint reads what's already stored — no external calls, no rate  #
# limit, instant — so the frontend can pre-populate results on load  #
# and they survive navigation.                                        #
# ------------------------------------------------------------------ #

@router.get("/bulk")
async def get_bulk_evidence(
    prediction_ids: str = Query(..., description="Comma-separated prediction IDs"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        ids = [int(x) for x in prediction_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="prediction_ids must be a comma-separated list of integers")

    if not ids:
        return {}

    pred_result = await db.execute(select(Prediction).where(Prediction.id.in_(ids)))
    predictions = {p.id: p for p in pred_result.scalars().all()}

    lit_result = await db.execute(
        select(LiteratureEvidence)
        .where(LiteratureEvidence.prediction_id.in_(ids))
        .order_by(LiteratureEvidence.created_at.desc())
    )
    clin_result = await db.execute(
        select(ClinicalEvidence)
        .where(ClinicalEvidence.prediction_id.in_(ids))
        .order_by(ClinicalEvidence.created_at.desc())
    )

    # Multiple "Validate" clicks over time create duplicate rows (same
    # pubmed_id/trial_id inserted again) since validate_prediction() never
    # checks for existing evidence first. Dedupe here so counts stay honest
    # regardless of how many times a row has been re-validated.
    lit_by_pred: dict[int, dict] = {}
    for ev in lit_result.scalars().all():
        lit_by_pred.setdefault(ev.prediction_id, {})
        lit_by_pred[ev.prediction_id].setdefault(ev.pubmed_id, ev)

    clin_by_pred: dict[int, dict] = {}
    for ev in clin_result.scalars().all():
        clin_by_pred.setdefault(ev.prediction_id, {})
        clin_by_pred[ev.prediction_id].setdefault(ev.trial_id, ev)

    bio_service = BiologicalValidationService(db)

    out: dict[int, dict] = {}
    for pid in ids:
        prediction = predictions.get(pid)
        literature_evidences = list(lit_by_pred.get(pid, {}).values())
        clinical_evidences = list(clin_by_pred.get(pid, {}).values())
        # Cheap, pure-DB computation — safe to always run fresh, no
        # external API / rate-limit concern.
        try:
            biological_result = await bio_service.validate_prediction(pid)
        except Exception as exc:
            logger.warning(f"Biological lookup failed for prediction {pid}: {exc}")
            biological_result = {}

        shaped = _shape_evidence(pid, literature_evidences, clinical_evidences, biological_result)
        # Distinguish "checked, found nothing" from "never checked" so the
        # frontend can still show a Validate button vs. real zero counts.
        shaped["ever_validated"] = bool(prediction and prediction.status != "pending")
        out[pid] = shaped

    return out


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
