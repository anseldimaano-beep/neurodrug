import httpx
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.domain import Prediction, ClinicalEvidence
from app.core.logging import logger


class ClinicalValidationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_url = "https://clinicaltrials.gov/api/v2"

    async def validate_prediction(self, prediction_id: int) -> List[ClinicalEvidence]:
        pred_result = await self.db.execute(select(Prediction).where(Prediction.id == prediction_id))
        prediction = pred_result.scalar_one_or_none()
        if not prediction or not prediction.drug or not prediction.disease:
            return []

        trials = await self._search_trials(prediction.disease.name, prediction.drug.name)

        evidences = []
        for trial in trials[:10]:
            ev = ClinicalEvidence(
                prediction_id=prediction_id,
                trial_id=trial.get("nctId", "unknown"),
                trial_phase=trial.get("phase"),
                recruitment_status=trial.get("status"),
                intervention=trial.get("intervention"),
                outcome_measure=trial.get("primaryOutcome")[:1000] if trial.get("primaryOutcome") else None,
                evidence_level="level_1" if trial.get("phase") in ["PHASE2", "PHASE3"] else "level_2",
                url=f"https://clinicaltrials.gov/study/{trial.get('nctId')}",
            )
            self.db.add(ev)
            evidences.append(ev)

        await self.db.commit()
        logger.info(f"Clinical validation for prediction {prediction_id}: {len(evidences)} trials found")
        return evidences

    async def _search_trials(self, condition: str, intervention: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/studies"
        params = {
            "query.cond": condition,
            "query.intr": intervention,
            "pageSize": 20,
            "format": "json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("studies", [])
