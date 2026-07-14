from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class ValidationRequest(BaseModel):
    prediction_id: int
    validation_types: List[str] = ["biological", "literature", "clinical"]


class ValidationResult(BaseModel):
    prediction_id: int
    validation_type: str
    overlap_score: Optional[float] = None
    evidence_count: Optional[int] = None
    details: Dict[str, Any] = {}
    status: str = "completed"
