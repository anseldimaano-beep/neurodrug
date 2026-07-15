from typing import Dict, List, Any
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
        builder = KnowledgeGraphBuilder(self.db)
        graph   = await builder.build_from_database(disease_efo_ids=[disease_efo_id])

        # Find disease node
        center = None
        for node in graph.nodes():
            if node.startswith("Disease:") and node[len("Disease:"):] == disease_efo_id:
                center = node
                break

        if not center:
            return {"disease": {"id": disease_efo_id, "name": "Not found", "type": "Disease"}, "nodes": [], "edges": []}

        sub = builder.get_subgraph(center, hops=depth)

        # Build edges first — only keep edges where both endpoints pass the type filter
        raw_edges = []
        for u, v, attr in sub.edges(data=True):
            u_type = sub.nodes[u].get("node_type", "Unknown")
            v_type = sub.nodes[v].get("node_type", "Unknown")
            if u_type == "Gene" and not include_genes: continue
            if v_type == "Gene" and not include_genes: continue
            if u_type == "Drug" and not include_drugs: continue
            if v_type == "Drug" and not include_drugs: continue
            raw_edges.append({
                "source": u,
                "target": v,
                "edge_type": attr.get("edge_type", "unknown"),
                "weight":    attr.get("weight", 1.0),
            })

        # Only include nodes that appear in at least one edge (excluding the center)
        connected_ids = set()
        for e in raw_edges:
            connected_ids.add(e["source"])
            connected_ids.add(e["target"])
        connected_ids.discard(center)

        filtered_nodes = []
        for n in connected_ids:
            attr      = sub.nodes[n]
            node_type = attr.get("node_type", "Unknown")
            if node_type == "Gene" and not include_genes: continue
            if node_type == "Drug" and not include_drugs: continue
            filtered_nodes.append({
                "id":        n,
                "name":      attr.get("name", n),
                "node_type": node_type,
                **attr.get("features", {}),
            })

        # Cap each node type independently so one type (e.g. Drug, via DGIdb's
        # dense gene-drug data) can't crowd out the others within max_nodes
        from collections import defaultdict
        by_type = defaultdict(list)
        for n in filtered_nodes:
            by_type[n["node_type"]].append(n)
        per_type_cap = max(max_nodes // len(by_type), 1) if by_type else max_nodes
        filtered_nodes = []
        for node_type, type_nodes in by_type.items():
            type_nodes.sort(key=lambda x: x["name"])
            filtered_nodes.extend(type_nodes[:per_type_cap])

        # Drop edges that reference capped-out nodes
        visible = {n["id"] for n in filtered_nodes} | {center}
        edges   = [e for e in raw_edges if e["source"] in visible and e["target"] in visible]

        disease_attr = graph.nodes[center]
        return {
            "disease": {
                "id":         f"Disease:{disease_efo_id}",
                "name":       disease_attr.get("name", disease_efo_id),
                "type":       "Disease",
                "properties": {k: v for k, v in disease_attr.items() if k != "features"},
            },
            "nodes": filtered_nodes,
            "edges": edges,
        }

    async def get_all_diseases(self) -> List[Dict[str, Any]]:
        builder = KnowledgeGraphBuilder(self.db)
        graph   = await builder.build_from_database()
        diseases = []
        for node, attr in graph.nodes(data=True):
            if node.startswith("Disease:"):
                efo_id = node[len("Disease:"):]
                diseases.append({"efo_id": efo_id, "name": attr.get("name", efo_id), "category": attr.get("category", "Unknown")})
        return sorted(diseases, key=lambda x: x["name"])

    async def find_paths(self, source: str, target: str, max_length: int = 4) -> Dict[str, Any]:
        builder = KnowledgeGraphBuilder(self.db)
        graph   = await builder.build_from_database()
        paths   = GraphQueryEngine(graph).find_paths(source, target, max_length)
        return {"paths": paths, "count": len(paths)}

    async def expand_node(self, node_id: str, depth: int = 1) -> Dict[str, Any]:
        builder = KnowledgeGraphBuilder(self.db)
        graph   = await builder.build_from_database()
        return GraphQueryEngine(graph).expand_node(node_id, depth)
