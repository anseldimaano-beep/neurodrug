from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.domain import Prediction, LiteratureEvidence, ClinicalEvidence
from app.core.logging import logger


class AIResearchAssistant:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def explain_prediction(self, prediction_id: int) -> Dict[str, Any]:
        pred_result = await self.db.execute(select(Prediction).where(Prediction.id == prediction_id))
        prediction = pred_result.scalar_one_or_none()
        if not prediction:
            return {"error": "Prediction not found"}

        lit_result = await self.db.execute(
            select(LiteratureEvidence).where(LiteratureEvidence.prediction_id == prediction_id)
        )
        lit = lit_result.scalars().all()

        clinical_result = await self.db.execute(
            select(ClinicalEvidence).where(ClinicalEvidence.prediction_id == prediction_id)
        )
        clin = clinical_result.scalars().all()

        explanation = {
            "prediction_id": prediction_id,
            "drug": prediction.drug.name if prediction.drug else None,
            "disease": prediction.disease.name if prediction.disease else None,
            "score": prediction.prediction_score,
            "summary": (
                f"The HGT model assigned a score of {prediction.prediction_score:.4f} to the drug-disease pair "
                f"({prediction.drug.name if prediction.drug else 'Unknown'}, {prediction.disease.name if prediction.disease else 'Unknown'}). "
                f"This score reflects the learned embedding similarity based on multi-omics graph topology."
            ),
            "supporting_literature": [
                {"pmid": l.pubmed_id, "title": l.title, "year": l.publication_year, "level": l.evidence_level}
                for l in lit
            ],
            "supporting_trials": [
                {"trial_id": c.trial_id, "phase": c.trial_phase, "status": c.recruitment_status, "level": c.evidence_level}
                for c in clin
            ],
            "biological_rationale": prediction.target_genes or [],
        }
        logger.info(f"Generated explanation for prediction {prediction_id}")
        return explanation

    async def summarize_publications(self, prediction_id: int) -> List[Dict[str, Any]]:
        lit_result = await self.db.execute(
            select(LiteratureEvidence).where(LiteratureEvidence.prediction_id == prediction_id)
        )
        return [
            {
                "pmid": l.pubmed_id,
                "title": l.title,
                "authors": l.authors,
                "journal": l.journal,
                "year": l.publication_year,
                "snippet": l.supporting_text[:500] if l.supporting_text else None,
            }
            for l in lit_result.scalars().all()
        ]
