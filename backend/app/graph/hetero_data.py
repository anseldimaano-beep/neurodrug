import torch
from torch_geometric.data import HeteroData
from typing import Dict, List, Tuple, Any
import numpy as np


class HeteroDataConverter:
    def __init__(self, node_feature_dims: Dict[str, int]):
        self.node_feature_dims = node_feature_dims

    def convert(self, nodes: Dict[str, List[Dict]], edges: Dict[Tuple[str, str, str], List[Tuple[int, int]]], features: Dict[str, np.ndarray]) -> HeteroData:
        data = HeteroData()

        for node_type, node_list in nodes.items():
            num_nodes = len(node_list)
            feat_dim = self.node_feature_dims.get(node_type, 8)
            if node_type in features:
                x = torch.from_numpy(features[node_type]).float()
            else:
                x = torch.randn(num_nodes, feat_dim)
            data[node_type].x = x
            data[node_type].node_names = [n["name"] for n in node_list]
            data[node_type].node_ids = [n["id"] for n in node_list]

        for (src, rel, dst), edge_list in edges.items():
            if len(edge_list) == 0:
                continue
            edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()
            data[src, rel, dst].edge_index = edge_index

        return data

    def add_negative_samples(self, data: HeteroData, src_type: str, dst_type: str, rel_type: str, num_negatives: int):
        num_src = data[src_type].x.size(0)
        num_dst = data[dst_type].x.size(0)
        neg_edges = []
        existing = set()
        edge_index = data[src_type, rel_type, dst_type].edge_index.t().tolist()
        for e in edge_index:
            existing.add((e[0], e[1]))

        rng = np.random.RandomState(42)
        while len(neg_edges) < num_negatives:
            s = rng.randint(0, num_src)
            d = rng.randint(0, num_dst)
            if (s, d) not in existing:
                neg_edges.append([s, d])
                existing.add((s, d))

        data[src_type, f"neg_{rel_type}", dst_type].edge_index = torch.tensor(neg_edges, dtype=torch.long).t().contiguous()
        return data
