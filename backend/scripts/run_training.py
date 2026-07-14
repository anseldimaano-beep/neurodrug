import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
import torch
from torch.utils.data import DataLoader
from app.ml.models.hgt import NeuroDrugHGT
from app.ml.trainer import HGTTrainer


def create_dummy_hetero_data():
    """
    Build a self-consistent dummy heterogeneous graph for training.

    Key constraints:
      1. Edge index row 0 (src) must be in [0, n_src)
         Edge index row 1 (dst) must be in [0, n_dst)
      2. Every node type must appear as a DESTINATION in at least one edge type.
         HGTConv only outputs features for destination node types; any source-only
         node type disappears from x_dict after the first conv layer, causing a
         KeyError in all subsequent layers.
         Fix: add reverse edges so Drug and Disease are also destinations.
    """
    from torch_geometric.data import HeteroData

    n_gene, n_drug, n_disease = 40, 30, 5
    hidden = 128

    data = HeteroData()
    data["Gene"].x    = torch.randn(n_gene,    hidden)
    data["Drug"].x    = torch.randn(n_drug,    hidden)
    data["Disease"].x = torch.randn(n_disease, hidden)

    def ei(n_src, n_dst, m):
        return torch.stack([
            torch.randint(0, n_src, (m,)),
            torch.randint(0, n_dst, (m,)),
        ])

    # --- forward edges ---
    data["Gene",    "PPI",            "Gene"   ].edge_index = ei(n_gene,    n_gene,    120)
    data["Drug",    "DrugTarget",     "Gene"   ].edge_index = ei(n_drug,    n_gene,     80)
    data["Gene",    "GeneDisease",    "Disease"].edge_index = ei(n_gene,    n_disease,  60)
    data["Drug",    "DrugDisease",    "Disease"].edge_index = ei(n_drug,    n_disease,  20)

    # --- reverse edges (make Drug and Disease also destination nodes) ---
    data["Gene",    "rev_DrugTarget",  "Drug"   ].edge_index = ei(n_gene,    n_drug,     80)
    data["Disease", "rev_GeneDisease", "Gene"   ].edge_index = ei(n_disease, n_gene,     60)
    data["Disease", "rev_DrugDisease", "Drug"   ].edge_index = ei(n_disease, n_drug,     20)

    return data


class DummyDataset(torch.utils.data.Dataset):
    def __init__(self, hetero_data, num_samples=200):
        self.data = hetero_data
        self.num_samples = num_samples
        self.n_drug    = hetero_data["Drug"].x.size(0)
        self.n_disease = hetero_data["Disease"].x.size(0)

    def __len__(self):
        return self.num_samples

    def __getitem__(self, idx):
        src = torch.randint(0, self.n_drug,    (32,))
        dst = torch.randint(0, self.n_disease, (32,))
        labels = torch.randint(0, 2, (32,)).float()

        class Batch:
            pass

        b = Batch()
        b.x_dict          = {k: self.data[k].x for k in self.data.node_types}
        b.edge_index_dict  = {k: self.data[k].edge_index for k in self.data.edge_types}
        b.src_nodes        = src
        b.dst_nodes        = dst
        b.src_type         = "Drug"
        b.dst_type         = "Disease"
        b.labels           = labels
        return b


async def main():
    data     = create_dummy_hetero_data()
    metadata = data.metadata()

    model   = NeuroDrugHGT(metadata=metadata, hidden_channels=128, num_layers=3, num_heads=4)
    trainer = HGTTrainer(model, device="cpu", max_epochs=5, patience=3)

    train_ds = DummyDataset(data, num_samples=200)
    val_ds   = DummyDataset(data, num_samples=50)

    # collate_fn=lambda x: x[0]  — batch_size=1, just unwrap the list
    train_loader = DataLoader(train_ds, batch_size=1, collate_fn=lambda x: x[0])
    val_loader   = DataLoader(val_ds,   batch_size=1, collate_fn=lambda x: x[0])

    trainer.fit(train_loader, val_loader)
    print("Training complete. Checkpoints saved to checkpoints/")


if __name__ == "__main__":
    asyncio.run(main())
