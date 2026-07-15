import httpx
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.domain import Prediction, ClinicalEvidence
from app.core.logging import logger


class ClinicalValidationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_url = "https://clinicaltrials.gov/api/v2"

    async def validate_prediction(self, prediction_id: int) -> List[ClinicalEvidence]:
        pred_result = await self.db.execute(
            select(Prediction)
            .options(
                selectinload(Prediction.drug),
                selectinload(Prediction.disease),
            )
            .where(Prediction.id == prediction_id)
        )
        prediction = pred_result.scalar_one_or_none()
        if not prediction or not prediction.drug or not prediction.disease:
            return []

        trials = await self._search_trials(prediction.disease.name, prediction.drug.name)

        # FIX C11: same duplicate-row issue as literature.py — skip trials
        # already stored for this prediction instead of re-inserting them
        # on every "Validate" click.
        existing_result = await self.db.execute(
            select(ClinicalEvidence.trial_id).where(
                ClinicalEvidence.prediction_id == prediction_id
            )
        )
        existing_trial_ids = {row[0] for row in existing_result.all()}

        new_evidences = []
        for trial in trials[:10]:
            # FIX C6: ClinicalTrials.gov API v2 nests everything under
            # protocolSection.<module>, not at the top level. Reading
            # trial.get("nctId") directly always returned None, which is
            # why every trial_id fell back to "unknown" and every url
            # became ".../study/None".
            protocol = trial.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            status_mod = protocol.get("statusModule", {})
            design_mod = protocol.get("designModule", {})
            arms_mod = protocol.get("armsInterventionsModule", {})
            outcomes_mod = protocol.get("outcomesModule", {})

            nct_id = ident.get("nctId")
            if not nct_id:
                # Can't build a real link or identify the trial — skip
                # rather than store an unusable "unknown" row.
                continue
            if nct_id in existing_trial_ids:
                # Already have this one on file — don't duplicate it.
                continue

            phases = design_mod.get("phases") or []
            phase = phases[0] if phases else None

            interventions = arms_mod.get("interventions") or []
            intervention_name = interventions[0].get("name") if interventions else None

            primary_outcomes = outcomes_mod.get("primaryOutcomes") or []
            outcome_measure = primary_outcomes[0].get("measure") if primary_outcomes else None

            ev = ClinicalEvidence(
                prediction_id=prediction_id,
                trial_id=nct_id,
                trial_phase=phase,
                recruitment_status=status_mod.get("overallStatus"),
                intervention=intervention_name,
                outcome_measure=outcome_measure[:1000] if outcome_measure else None,
                evidence_level="level_1" if phase in ["PHASE2", "PHASE3"] else "level_2",
                url=f"https://clinicaltrials.gov/study/{nct_id}",
            )
            self.db.add(ev)
            new_evidences.append(ev)

        # Return the FULL set (existing + newly added), not just what was
        # inserted this call.
        if existing_trial_ids or new_evidences:
            existing_evidences_result = await self.db.execute(
                select(ClinicalEvidence).where(
                    ClinicalEvidence.prediction_id == prediction_id,
                    ClinicalEvidence.trial_id.in_(existing_trial_ids),
                )
            )
            evidences = list(existing_evidences_result.scalars().all()) + new_evidences
        else:
            evidences = new_evidences

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
