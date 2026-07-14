from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, Dict, Any


class ETLJobCreate(BaseModel):
    source_name: str
    parameters: Optional[Dict[str, Any]] = {}


class ETLJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_name: str
    status: str
    records_processed: int
    records_inserted: int
    records_failed: int
    error_log: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
