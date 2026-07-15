import random
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GCNConv, RGCNConv, GATConv, SAGEConv, HANConv
from sklearn.decomposition import NMF
from collections import defaultdict


class RandomBaseline:
    def predict(self, pairs):
        return np.random.rand(len(pairs))


class JaccardBaseline:
    def __init__(self, adjacency_dict):
        self.adj = adjacency_dict

    def predict(self, pairs):
        scores = []
        for u, v in pairs:
            neighbors_u = set(self.adj.get(u, []))
            neighbors_v = set(self.adj.get(v, []))
            inter = len(neighbors_u & neighbors_v)
            union = len(neighbors_u | neighbors_v)
            scores.append(inter / union if union > 0 else 0.0)
        return np.array(scores)


class AdamicAdarBaseline:
    def __init__(self, adjacency_dict):
        self.adj = adjacency_dict
        self.degree = {n: len(neighbors) for n, neighbors in adjacency_dict.items()}

    def predict(self, pairs):
        scores = []
        for u, v in pairs:
            neighbors_u = set(self.adj.get(u, []))
            neighbors_v = set(self.adj.get(v, []))
            score = sum(1 / np.log(self.degree.get(w, 2)) for w in neighbors_u & neighbors_v if self.degree.get(w, 2) > 1)
            scores.append(score)
        return np.array(scores)


class MatrixFactorizationBaseline:
    def __init__(self, n_components=64, max_iter=500):
        self.n_components = n_components
        self.max_iter = max_iter
        self.model = None

    def fit(self, interaction_matrix):
        self.model = NMF(n_components=self.n_components, max_iter=self.max_iter, init="random", random_state=42)
        self.W = self.model.fit_transform(interaction_matrix)
        self.H = self.model.components_

    def predict(self, pairs):
        scores = []
        for u, v in pairs:
            if u < self.W.shape[0] and v < self.H.shape[1]:
                scores.append(np.dot(self.W[u], self.H[:, v]))
            else:
                scores.append(0.0)
        return np.array(scores)


class HomogeneousGCN(nn.Module):
    def __init__(self, in_channels, hidden_channels, out_channels, num_layers=2):
        super().__init__()
        self.convs = nn.ModuleList()
        self.convs.append(GCNConv(in_channels, hidden_channels))
        for _ in range(num_layers - 2):
            self.convs.append(GCNConv(hidden_channels, hidden_channels))
        self.convs.append(GCNConv(hidden_channels, out_channels))

    def forward(self, x, edge_index):
        for conv in self.convs[:-1]:
            x = F.relu(conv(x, edge_index))
            x = F.dropout(x, p=0.5, training=self.training)
        x = self.convs[-1](x, edge_index)
        return x


class RGCNBaseline(nn.Module):
    def __init__(self, in_channels, hidden_channels, out_channels, num_relations, num_layers=2):
        super().__init__()
        self.convs = nn.ModuleList()
        self.convs.append(RGCNConv(in_channels, hidden_channels, num_relations, num_bases=30))
        for _ in range(num_layers - 2):
            self.convs.append(RGCNConv(hidden_channels, hidden_channels, num_relations, num_bases=30))
        self.convs.append(RGCNConv(hidden_channels, out_channels, num_relations, num_bases=30))

    def forward(self, x, edge_index, edge_type):
        for conv in self.convs[:-1]:
            x = F.relu(conv(x, edge_index, edge_type))
            x = F.dropout(x, p=0.5, training=self.training)
        x = self.convs[-1](x, edge_index, edge_type)
        return x


class GraphSAGEBaseline(nn.Module):
    def __init__(self, in_channels, hidden_channels, out_channels, num_layers=2):
        super().__init__()
        self.convs = nn.ModuleList()
        self.convs.append(SAGEConv(in_channels, hidden_channels))
        for _ in range(num_layers - 2):
            self.convs.append(SAGEConv(hidden_channels, hidden_channels))
        self.convs.append(SAGEConv(hidden_channels, out_channels))

    def forward(self, x, edge_index):
        for conv in self.convs[:-1]:
            x = F.relu(conv(x, edge_index))
            x = F.dropout(x, p=0.5, training=self.training)
        x = self.convs[-1](x, edge_index)
        return x


class GATBaseline(nn.Module):
    def __init__(self, in_channels, hidden_channels, out_channels, heads=4, num_layers=2):
        super().__init__()
        self.convs = nn.ModuleList()
        self.convs.append(GATConv(in_channels, hidden_channels, heads=heads, concat=False))
        for _ in range(num_layers - 2):
            self.convs.append(GATConv(hidden_channels, hidden_channels, heads=heads, concat=False))
        self.convs.append(GATConv(hidden_channels, out_channels, heads=1, concat=False))

    def forward(self, x, edge_index):
        for conv in self.convs[:-1]:
            x = F.relu(conv(x, edge_index))
            x = F.dropout(x, p=0.5, training=self.training)
        x = self.convs[-1](x, edge_index)
        return x


class HANBaseline(nn.Module):
    """
    Heterogeneous Graph Attention Network (Wang et al., 2019) -- the sixth
    baseline named in the proposal's Phase 3 evaluation plan
    (Random / Jaccard / Matrix Factorization / GCN / R-GCN / HAN).

    Mirrors HeteroGNNEncoder's carry-forward pattern: HANConv, like HGTConv,
    only returns updated embeddings for node types that appear as message
    *destinations*. Nodes that are purely source-side keep their previous
    embedding unchanged for that layer so every node type always has a
    representation, matching how NeuroDrugHGT handles the same issue.
    """

    def __init__(
        self,
        metadata: tuple,
        hidden_channels: int = 128,
        out_channels: int = 128,
        num_layers: int = 2,
        heads: int = 4,
        dropout: float = 0.5,
    ):
        super().__init__()
        self.node_types, self.edge_types = metadata
        self.dropout = dropout

        self.lin_dict = nn.ModuleDict()
        for node_type in self.node_types:
            self.lin_dict[node_type] = nn.LazyLinear(hidden_channels)

        self.convs = nn.ModuleList()
        for i in range(num_layers):
            out_c = out_channels if i == num_layers - 1 else hidden_channels
            self.convs.append(
                HANConv(
                    in_channels=hidden_channels,
                    out_channels=out_c,
                    metadata=metadata,
                    heads=heads,
                    dropout=dropout,
                )
            )

    def forward(self, x_dict, edge_index_dict):
        x_dict = {k: F.relu(self.lin_dict[k](x)) for k, x in x_dict.items()}

        for conv in self.convs:
            out_dict = conv(x_dict, edge_index_dict)
            new_x_dict = {}
            for k, x_prev in x_dict.items():
                if k in out_dict and out_dict[k] is not None:
                    new_x_dict[k] = F.dropout(out_dict[k], p=self.dropout, training=self.training)
                else:
                    new_x_dict[k] = x_prev
            x_dict = new_x_dict

        return x_dict


class HANLinkPredictor(nn.Module):
    """Full HAN model + MLP link predictor, structured like NeuroDrugHGT
    (backend/app/ml/models/hgt.py) so it drops into the same training/eval
    loop for a head-to-head baseline comparison against the HGT model."""

    def __init__(self, metadata: tuple, hidden_channels: int = 128, num_layers: int = 2, heads: int = 4):
        super().__init__()
        self.encoder = HANBaseline(
            metadata=metadata,
            hidden_channels=hidden_channels,
            out_channels=hidden_channels,
            num_layers=num_layers,
            heads=heads,
        )
        self.predictor = nn.Sequential(
            nn.Linear(hidden_channels * 2, hidden_channels // 2),
            nn.LayerNorm(hidden_channels // 2),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_channels // 2, hidden_channels // 4),
            nn.LayerNorm(hidden_channels // 4),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_channels // 4, 1),
        )

    def forward(self, x_dict, edge_index_dict, src_nodes, dst_nodes, src_type, dst_type):
        emb_dict = self.encoder(x_dict, edge_index_dict)
        src_emb = emb_dict[src_type][src_nodes]
        dst_emb = emb_dict[dst_type][dst_nodes]
        z = torch.cat([src_emb, dst_emb], dim=-1)
        return self.predictor(z).squeeze(-1)
