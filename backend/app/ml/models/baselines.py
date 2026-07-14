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
