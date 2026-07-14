from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class NodeSchema(BaseModel):
    id: str
    name: str
    node_type: str
    features: Optional[Dict[str, Any]] = None


class EdgeSchema(BaseModel):
    source: str
    target: str
    edge_type: str
    weight: float = 1.0


class DiseaseSchema(BaseModel):
    id: str
    name: str
    type: str = "Disease"
    properties: Optional[Dict[str, Any]] = None


class SubgraphResponse(BaseModel):
    disease: DiseaseSchema
    nodes: List[NodeSchema]
    edges: List[EdgeSchema]