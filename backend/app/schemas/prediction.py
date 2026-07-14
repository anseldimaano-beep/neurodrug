from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class PredictionBase(BaseModel):
    drug_id: int
    disease_id: int
    prediction_score: float = Field(..., ge=0.0, le=1.0)
    confidence_score: Optional[float] = None
    novelty_score: Optional[float] = None
    rank: Optional[int] = None


class PredictionCreate(PredictionBase):
    model_version_id: int


class PredictionResponse(PredictionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    model_version_id: int
    status: str
    target_genes: Optional[List[str]] = None
    affected_pathways: Optional[List[str]] = None
    created_at: datetime
    drug: Optional[Dict[str, Any]] = None
    disease: Optional[Dict[str, Any]] = None


class RepurposingRequest(BaseModel):
    disease_efo_id: str = Field(..., description="EFO disease identifier")
    model_version_id: int = Field(..., description="Model version to use for inference")
    top_k: int = Field(default=20, ge=1, le=200)


class RepurposingResponse(BaseModel):
    disease: str
    candidates: List[Dict[str, Any]]
    total: int
    model_version_id: int
