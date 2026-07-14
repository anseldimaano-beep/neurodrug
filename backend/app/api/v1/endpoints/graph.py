from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from app.services.graph_service import GraphService
from app.schemas.graph import SubgraphResponse

router = APIRouter()


@router.get("/subgraph", response_model=SubgraphResponse)
async def get_disease_subgraph(
    disease_efo_id: str = Query(..., description="EFO ID of disease to filter by"),
    include_genes: bool = Query(True),
    include_drugs: bool = Query(True),
    max_nodes: int = Query(500, ge=50, le=2000),
    depth: int = Query(2, ge=1, le=3)
):
    """
    Return disease-specific subgraph.
    Only returns nodes connected to the specified disease EFO ID.
    """
    service = GraphService()

    try:
        subgraph = await service.get_subgraph_by_disease(
            disease_efo_id=disease_efo_id,
            include_genes=include_genes,
            include_drugs=include_drugs,
            max_nodes=max_nodes,
            depth=depth
        )
        return subgraph

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {str(e)}")


@router.get("/diseases")
async def list_available_diseases():
    """Return all diseases available in the KG for tab population."""
    service = GraphService()
    return await service.get_all_diseases()