import csv
import json
from typing import List, Dict, Any
from io import StringIO
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.domain import Prediction, Disease
from app.core.logging import logger


class ScientificReportingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_prediction_csv(self, disease_efo_id: str) -> str:
        disease_result = await self.db.execute(select(Disease).where(Disease.efo_id == disease_efo_id))
        disease = disease_result.scalar_one_or_none()
        if not disease:
            return ""

        pred_result = await self.db.execute(
            select(Prediction)
            .where(Prediction.disease_id == disease.id)
            .where(Prediction.is_deleted == False)
            .order_by(Prediction.prediction_score.desc())
        )
        predictions = pred_result.scalars().all()

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["rank", "drug_name", "prediction_score", "confidence_score", "novelty_score", "evidence_score", "status", "target_genes", "affected_pathways"])
        for p in predictions:
            writer.writerow([
                p.rank,
                p.drug.name if p.drug else "",
                p.prediction_score,
                p.confidence_score,
                p.novelty_score,
                p.evidence_score,
                p.status,
                "|".join(p.target_genes or []),
                "|".join(p.affected_pathways or []),
            ])
        return output.getvalue()

    async def generate_summary_json(self, disease_efo_id: str) -> Dict[str, Any]:
        disease_result = await self.db.execute(select(Disease).where(Disease.efo_id == disease_efo_id))
        disease = disease_result.scalar_one_or_none()
        if not disease:
            return {}

        pred_result = await self.db.execute(
            select(Prediction).where(Prediction.disease_id == disease.id).where(Prediction.is_deleted == False)
        )
        predictions = pred_result.scalars().all()

        validated = [p for p in predictions if p.status == "validated"]
        novel = [p for p in predictions if p.status == "novel"]

        return {
            "disease": disease.name,
            "efo_id": disease.efo_id,
            "total_predictions": len(predictions),
            "validated_count": len(validated),
            "novel_count": len(novel),
            "top_10": [
                {
                    "rank": p.rank,
                    "drug": p.drug.name if p.drug else None,
                    "score": p.prediction_score,
                    "confidence": p.confidence_score,
                }
                for p in predictions[:10]
            ],
        }
