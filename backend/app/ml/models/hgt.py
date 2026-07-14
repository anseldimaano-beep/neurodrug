import torch
import torch.nn as nn
from torch_geometric.nn import HGTConv, Linear
from torch_geometric.data import HeteroData


class HeteroGNNEncoder(nn.Module):
    def __init__(
        self,
        metadata: tuple,
        hidden_channels: int = 128,
        out_channels: int = 128,
        num_layers: int = 3,
        num_heads: int = 4,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.node_types, self.edge_types = metadata
        self.num_layers = num_layers
        self.dropout = dropout

        self.lin_dict = nn.ModuleDict()
        for node_type in self.node_types:
            self.lin_dict[node_type] = Linear(-1, hidden_channels)

        self.convs = nn.ModuleList()
        for _ in range(num_layers):
            conv = HGTConv(
                in_channels=hidden_channels,
                out_channels=hidden_channels,
                metadata=metadata,
                heads=num_heads,
            )
            self.convs.append(conv)

        self.norms = nn.ModuleList()
        for _ in range(num_layers):
            self.norms.append(nn.LayerNorm(hidden_channels))

        self.projections = nn.ModuleDict()
        for node_type in self.node_types:
            self.projections[node_type] = nn.Sequential(
                nn.Linear(hidden_channels, out_channels),
                nn.LayerNorm(out_channels),
            )

    def forward(self, x_dict, edge_index_dict):
        x_dict = {key: self.lin_dict[key](x).relu() for key, x in x_dict.items()}

        for conv, norm in zip(self.convs, self.norms):
            x_dict_prev = x_dict
            conv_out = conv(x_dict, edge_index_dict)

            # HGTConv only returns node types that appear as message
            # *destinations* in at least one edge type.  Node types that are
            # purely source-side (e.g. Drug, which only targets Gene/Disease
            # but is never a target itself) are silently absent from conv_out.
            # We restore them here so downstream code can always find every
            # node type in x_dict.
            new_x_dict: dict = {}
            for key, x_prev in x_dict_prev.items():
                if key in conv_out and conv_out[key] is not None:
                    # Normal path: normalise, activate, residual
                    new_x_dict[key] = norm(conv_out[key]).relu() + x_prev
                else:
                    # No incoming messages — carry embeddings forward unchanged
                    new_x_dict[key] = x_prev

            if self.dropout > 0:
                new_x_dict = {
                    key: nn.functional.dropout(x, p=self.dropout, training=self.training)
                    for key, x in new_x_dict.items()
                }
            x_dict = new_x_dict

        x_dict = {key: self.projections[key](x) for key, x in x_dict.items()}
        return x_dict


class LinkPredictor(nn.Module):
    def __init__(self, in_channels: int = 128, hidden_channels: int = 64, dropout: float = 0.3):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(in_channels * 2, hidden_channels),
            nn.LayerNorm(hidden_channels),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_channels, hidden_channels // 2),
            nn.LayerNorm(hidden_channels // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_channels // 2, 1),
        )

    def forward(self, src_emb, dst_emb):
        z = torch.cat([src_emb, dst_emb], dim=-1)
        return self.mlp(z).squeeze(-1)


class NeuroDrugHGT(nn.Module):
    def __init__(self, metadata: tuple, hidden_channels: int = 128, num_layers: int = 3, num_heads: int = 4):
        super().__init__()
        self.encoder = HeteroGNNEncoder(
            metadata=metadata,
            hidden_channels=hidden_channels,
            out_channels=hidden_channels,
            num_layers=num_layers,
            num_heads=num_heads,
        )
        self.predictor = LinkPredictor(in_channels=hidden_channels)

    def forward(self, x_dict, edge_index_dict, src_nodes, dst_nodes, src_type, dst_type):
        emb_dict = self.encoder(x_dict, edge_index_dict)
        src_emb = emb_dict[src_type][src_nodes]
        dst_emb = emb_dict[dst_type][dst_nodes]
        return self.predictor(src_emb, dst_emb)

    def encode(self, x_dict, edge_index_dict):
        return self.encoder(x_dict, edge_index_dict)
