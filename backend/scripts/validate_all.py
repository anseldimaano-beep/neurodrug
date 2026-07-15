"""
validate_all.py — Run literature/clinical/biological validation for every
prediction across every disease (or one disease with --disease), directly
against the DB instead of clicking through the UI tab-by-tab.

Reuses the same LiteratureValidationService / ClinicalValidationService /
BiologicalValidationService as the /validation/run API endpoint, so results
land in the same tables and show up in the UI immediately afterward (via
GET /validation/bulk).

Usage (from inside the api container):
    docker-compose exec api python scripts/validate_all.py
    docker-compose exec api python scripts/validate_all.py --disease MONDO_0005072
    docker-compose exec api python scripts/validate_all.py --force   # re-validate even if already done
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select

from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.models.domain import Prediction, Disease
from app.services.validation.literature import LiteratureValidationService
from app.services.validation.clinical import ClinicalValidationService
from app.services.validation.biological import BiologicalValidationService

# Gap between predictions — same 800ms used by the "Validate All" button in
# the UI, tuned to stay under NCBI's ~3 req/sec limit now that literature.py
# batches its PubMed lookups into a single esummary call.
DELAY_SECONDS = 0.8


async def validate_one(db, prediction: Prediction) -> dict:
    lit_service = LiteratureValidationService(db)
    clin_service = ClinicalValidationService(db)
    bio_service = BiologicalValidationService(db)

    errors = {}
    try:
        lit = await lit_service.validate_prediction(prediction.id)
    except Exception as exc:
        logger.warning(f"  literature failed for prediction {prediction.id}: {exc}")
        lit, errors["literature"] = [], str(exc)

    try:
        clin = await clin_service.validate_prediction(prediction.id)
    except Exception as exc:
        logger.warning(f"  clinical failed for prediction {prediction.id}: {exc}")
        clin, errors["clinical"] = [], str(exc)

    try:
        await bio_service.validate_prediction(prediction.id)
    except Exception as exc:
        logger.warning(f"  biological failed for prediction {prediction.id}: {exc}")
        errors["biological"] = str(exc)

    return {"literature": len(lit), "clinical": len(clin), "errors": errors}


async def main(disease_efo_id: str | None, force: bool) -> None:
    async with AsyncSessionLocal() as db:
        query = select(Prediction).where(Prediction.is_deleted == False)
        if disease_efo_id:
            disease_result = await db.execute(select(Disease).where(Disease.efo_id == disease_efo_id))
            disease = disease_result.scalar_one_or_none()
            if not disease:
                logger.error(f"No disease found with efo_id={disease_efo_id}")
                return
            query = query.where(Prediction.disease_id == disease.id)
        if not force:
            query = query.where(Prediction.status == "pending")

        result = await db.execute(query)
        predictions = result.scalars().all()

        if not predictions:
            logger.info("Nothing to validate (use --force to re-validate already-checked predictions).")
            return

        logger.info(f"Validating {len(predictions)} predictions...")
        ok, failed = 0, 0
        for i, pred in enumerate(predictions, start=1):
            logger.info(f"[{i}/{len(predictions)}] prediction_id={pred.id} (drug_id={pred.drug_id}, disease_id={pred.disease_id})")
            res = await validate_one(db, pred)
            if res["errors"]:
                failed += 1
            else:
                ok += 1
            logger.info(f"  -> literature={res['literature']} clinical={res['clinical']} errors={res['errors'] or 'none'}")
            await asyncio.sleep(DELAY_SECONDS)

        logger.info(f"Done. {ok} succeeded cleanly, {failed} had at least one partial failure (see warnings above).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--disease", type=str, default=None, help="EFO/MONDO id to restrict to one disease (default: all diseases).")
    parser.add_argument("--force", action="store_true", help="Re-validate predictions that already have a non-pending status.")
    args = parser.parse_args()
    asyncio.run(main(args.disease, args.force))
