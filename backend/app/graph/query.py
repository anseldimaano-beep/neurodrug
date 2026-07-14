from typing import List, Dict, Any, Optional
import networkx as nx
from app.core.logging import logger


class GraphQueryEngine:
    def __init__(self, nx_graph: nx.MultiDiGraph):
        self.graph = nx_graph

    def find_paths(self, source: str, target: str, max_length: int = 4) -> List[List[str]]:
        try:
            paths = list(nx.all_simple_paths(self.graph, source, target, cutoff=max_length))
            return paths
        except nx.NetworkXNoPath:
            return []

    def get_neighbors(self, node: str, edge_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        if node not in self.graph:
            return []
        neighbors = []
        for _, v, key, attr in self.graph.out_edges(node, keys=True, data=True):
            if edge_types is None or attr.get("edge_type") in edge_types:
                neighbors.append({
                    "node": v,
                    "edge_type": attr.get("edge_type"),
                    "weight": attr.get("weight", 1.0),
                    "direction": "out",
                })
        for u, _, key, attr in self.graph.in_edges(node, keys=True, data=True):
            if edge_types is None or attr.get("edge_type") in edge_types:
                neighbors.append({
                    "node": u,
                    "edge_type": attr.get("edge_type"),
                    "weight": attr.get("weight", 1.0),
                    "direction": "in",
                })
        return neighbors

    def expand_node(self, node: str, depth: int = 1) -> Dict[str, Any]:
        if node not in self.graph:
            return {"node": node, "exists": False}
        subgraph_nodes = {node}
        for _ in range(depth):
            new_nodes = set()
            for n in subgraph_nodes:
                new_nodes.update(self.graph.predecessors(n))
                new_nodes.update(self.graph.successors(n))
            subgraph_nodes.update(new_nodes)
        sub = self.graph.subgraph(subgraph_nodes).copy()
        return {
            "node": node,
            "exists": True,
            "subgraph_nodes": list(sub.nodes(data=True)),
            "subgraph_edges": [
                {"source": u, "target": v, **attr} for u, v, attr in sub.edges(data=True)
            ],
        }

    def get_drug_target_edges(self, drug_name: str) -> List[Dict]:
        drug_node = f"Drug:{drug_name}"
        return self.get_neighbors(drug_node, edge_types=["DrugTarget"])

    def get_gene_disease_edges(self, gene_symbol: str) -> List[Dict]:
        gene_node = f"Gene:{gene_symbol}"
        return self.get_neighbors(gene_node, edge_types=["GeneDisease"])
