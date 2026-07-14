from typing import Dict, List, Any
import networkx as nx
from app.graph.builder import KnowledgeGraphBuilder
from app.graph.query import GraphQueryEngine
from sqlalchemy.ext.asyncio import AsyncSession


class GraphService:
    def __init__(self, db: AsyncSession = None):
        self.db = db

    async def get_subgraph_by_disease(
        self,
        disease_efo_id: str,
        include_genes: bool = True,
        include_drugs: bool = True,
        max_nodes: int = 500,
        depth: int = 2
    ) -> Dict[str, Any]:
        """
        Return disease-specific subgraph.
        ONLY returns nodes connected to the specified disease EFO ID.
        """
        builder = KnowledgeGraphBuilder(self.db)
        
        # PASS disease_efo_ids to builder — this was missing!
        graph = await builder.build_from_database(disease_efo_ids=[disease_efo_id])

        # Find the disease node by EXACT EFO ID match
        center = None
        for node in graph.nodes():
            if not node.startswith("Disease:"):
                continue
            node_efo_id = node[len("Disease:"):]
            if node_efo_id == disease_efo_id:
                center = node
                break

        if not center:
            return {
                "disease": {
                    "id": disease_efo_id,
                    "name": "Not found",
                    "type": "Disease"
                },
                "nodes": [],
                "edges": []
            }

        # Get subgraph centered on this disease
        sub = builder.get_subgraph(center, hops=depth)

        # Filter nodes by type if requested
        filtered_nodes = []
        for n, attr in sub.nodes(data=True):
            node_type = attr.get("node_type", "Unknown")
            
            if node_type == "Gene" and not include_genes:
                continue
            if node_type == "Drug" and not include_drugs:
                continue
            
            filtered_nodes.append({
                "id": n,
                "name": attr.get("name", n),
                "node_type": node_type,
                **attr.get("features", {}),
            })

        filtered_nodes = filtered_nodes[:max_nodes]

        edges = []
        for u, v, attr in sub.edges(data=True):
            edges.append({
                "source": u,
                "target": v,
                "edge_type": attr.get("edge_type", "unknown"),
                "weight": attr.get("weight", 1.0),
            })

        disease_attr = graph.nodes[center]
        
        return {
            "disease": {
                "id": disease_efo_id,
                "name": disease_attr.get("name", disease_efo_id),
                "type": "Disease",
                "properties": {k: v for k, v in disease_attr.items() if k != "features"}
            },
            "nodes": filtered_nodes,
            "edges": edges
        }

    async def get_all_diseases(self) -> List[Dict[str, Any]]:
        """Return all diseases available in the KG for tab population."""
        builder = KnowledgeGraphBuilder(self.db)
        graph = await builder.build_from_database()  # No filter — get all diseases
        
        diseases = []
        for node, attr in graph.nodes(data=True):
            if node.startswith("Disease:"):
                efo_id = node[len("Disease:"):]
                diseases.append({
                    "efo_id": efo_id,
                    "name": attr.get("name", efo_id),
                    "category": attr.get("category", "Unknown")
                })
        
        return sorted(diseases, key=lambda x: x["name"])

    async def find_paths(self, source: str, target: str, max_length: int = 4) -> Dict[str, Any]:
        builder = KnowledgeGraphBuilder(self.db)
        graph = await builder.build_from_database()
        engine = GraphQueryEngine(graph)
        paths = engine.find_paths(source, target, max_length)
        return {"paths": paths, "count": len(paths)}

    async def expand_node(self, node_id: str, depth: int = 1) -> Dict[str, Any]:
        builder = KnowledgeGraphBuilder(self.db)
        graph = await builder.build_from_database()
        engine = GraphQueryEngine(graph)
        return engine.expand_node(node_id, depth)