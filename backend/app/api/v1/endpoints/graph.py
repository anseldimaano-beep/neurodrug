from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.graph_service import GraphService
from app.schemas.graph import SubgraphResponse
from app.api.deps import get_db

router = APIRouter()

@router.get("/subgraph", response_model=SubgraphResponse)
async def get_disease_subgraph(
    disease_efo_id: Optional[str] = Query(None),
    disease_id: Optional[str] = Query(None),
    include_genes: bool = Query(True),
    include_drugs: bool = Query(True),
    max_nodes: int = Query(500, ge=50, le=2000),
    depth: int = Query(2, ge=1, le=3),
    hops: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    efo_id = disease_efo_id or disease_id
    if not efo_id:
        raise HTTPException(status_code=422, detail="disease_efo_id or disease_id required")
    service = GraphService(db)
    try:
        result = await service.get_subgraph_by_disease(
            disease_efo_id=efo_id,
            include_genes=include_genes,
            include_drugs=include_drugs,
            max_nodes=max_nodes,
            depth=hops if hops is not None else depth
        )
        node_ids = {n["id"] for n in result["nodes"]}
        node_ids.add(f"Disease:{efo_id}")
        result["edges"] = [
            e for e in result["edges"]
            if e["source"] in node_ids and e["target"] in node_ids
        ]
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {str(e)}")

@router.get("/diseases")
async def list_available_diseases(db: AsyncSession = Depends(get_db)):
    service = GraphService(db)
    return await service.get_all_diseases()


@router.get("/stats")
async def get_graph_stats(db: AsyncSession = Depends(get_db)):
    """
    High-level statistics for the full knowledge graph.
    Called by api.ts getGraphStats().
    """
    from app.graph.builder import KnowledgeGraphBuilder
    builder = KnowledgeGraphBuilder(db)
    graph = await builder.build_from_database()  # no disease filter — whole graph
    return builder.get_statistics()
