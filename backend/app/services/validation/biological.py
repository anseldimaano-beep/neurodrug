from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.domain import Prediction, Interaction, Gene, Drug, Disease
from app.core.logging import logger


class BiologicalValidationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_prediction(self, prediction_id: int) -> Dict[str, Any]:
        pred_result = await self.db.execute(select(Prediction).where(Prediction.id == prediction_id))
        prediction = pred_result.scalar_one_or_none()
        if not prediction or not prediction.drug or not prediction.disease:
            return {}

        drug_id = prediction.drug_id
        disease_id = prediction.disease_id

        target_result = await self.db.execute(
            select(Interaction)
            .where(Interaction.drug_id == drug_id)
            .where(Interaction.interaction_type == "DrugTarget")
        )
        targets = target_result.scalars().all()
        target_genes = [t.source_gene.symbol for t in targets if t.source_gene]

        disease_assoc_result = await self.db.execute(
            select(Interaction)
            .where(Interaction.disease_id == disease_id)
            .where(Interaction.interaction_type == "GeneDisease")
        )
        disease_genes = [a.source_gene.symbol for a in disease_assoc_result.scalars().all() if a.source_gene]

        overlap = set(target_genes) & set(disease_genes)
        overlap_score = len(overlap) / max(len(target_genes), 1)

        rationale = f"Drug targets {len(target_genes)} genes. {len(overlap)} overlap with disease-associated genes ({', '.join(list(overlap)[:5])})."

        result = {
            "prediction_id": prediction_id,
            "target_genes": target_genes,
            "disease_genes": disease_genes,
            "overlap_count": len(overlap),
            "overlap_score": overlap_score,
            "biological_rationale": rationale,
            "pathway_coverage": "pending",
        }
        prediction.target_genes = list(overlap)
        await self.db.commit()
        logger.info(f"Biological validation for prediction {prediction_id}: overlap={len(overlap)}")
        return result
