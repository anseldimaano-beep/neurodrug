from typing import List, Dict, Any
import numpy as np


class PredictionRanker:
    @staticmethod
    def compute_novelty_score(prediction_score: float, known_evidence_count: int) -> float:
        return prediction_score * (1.0 / (1.0 + np.log1p(known_evidence_count)))

    @staticmethod
    def compute_confidence_score(prediction_score: float, model_auc: float, evidence_score: float) -> float:
        return 0.5 * prediction_score + 0.3 * model_auc + 0.2 * evidence_score

    @staticmethod
    def rerank(
        predictions: List[Dict[str, Any]],
        model_auc: float = 0.85,
        evidence_map: Dict[str, int] = None,
    ) -> List[Dict[str, Any]]:
        evidence_map = evidence_map or {}
        scored = []
        for pred in predictions:
            drug = pred["drug_name"]
            ev_count = evidence_map.get(drug, 0)
            novelty = PredictionRanker.compute_novelty_score(pred["prediction_score"], ev_count)
            confidence = PredictionRanker.compute_confidence_score(
                pred["prediction_score"], model_auc, pred.get("evidence_score", 0.0)
            )
            scored.append({
                **pred,
                "novelty_score": float(novelty),
                "confidence_score": float(confidence),
            })
        scored.sort(key=lambda x: x["confidence_score"], reverse=True)
        for i, s in enumerate(scored):
            s["rank"] = i + 1
        return scored
