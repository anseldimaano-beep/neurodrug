"""
run_training.py — Real-graph HGT training
==========================================
Loads the full knowledge graph from PostgreSQL (all five pediatric cancer
diseases), converts it to a PyG HeteroData object, and trains NeuroDrugHGT
on real Drug-Disease link-prediction pairs.

Usage (from the Docker container):
    docker-compose exec api python scripts/run_training.py

Requirements: ETL ingestion must have run so Drug-Disease edges exist.

FIXES applied in this version
------------------------------
FIX-T1  _disease_feats was returning [1.0, 0, 0, …] for EVERY disease,
         giving all disease nodes identical input features.  The model
         could only distinguish diseases via graph structure, not features,
         which severely limited score diversity.  Now each disease gets a
         unique 5-dim one-hot vector (padded to FEATURE_DIM).

FIX-T2  nx_to_heterodata now injects '_node_key' into the attrs dict
         passed to feature functions so _disease_feats can parse the
         MONDO ID from the node key (e.g. "Disease:MONDO_0018177").

FIX-T3  HGTTrainer is now passed graph metadata so save_checkpoint
         embeds it in the .pt file.  predictor.load_checkpoint can then
         warn early if inference topology doesn't match training topology.

Methodology (matches the paper's Methods section)
---------------------------------------------------
Drug-Disease edges are randomly split into 70% training, 15% validation, and
15% test sets (see `build_splits`). For each positive drug-disease edge in a
batch, an equal number of negative edges are sampled by pairing the existing
disease node with a randomly selected drug node (head/drug-side corruption —
see `sample_negatives`), so training directly matches the target task of
ranking candidate drugs for a disease. The training set resamples negatives
fresh every batch, while val/test use a fixed negative set for reproducible
metrics. The loss function is binary cross-entropy with logits applied to
positive and negative edge scores (see HGTTrainer.train_epoch in
app/ml/trainer.py). Training hyperparameters: learning rate 3e-4, AdamW
optimizer (weight decay 1e-5), cosine annealing scheduler (T_max = 200
epochs, eta_min = 1e-5), gradient clipping (max norm = 1.0), early stopping
with patience = 25 epochs on validation AUC. Experiments were run on a
Google Colab T4 GPU.
"""

import argparse
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import numpy as np
import torch
from collections import defaultdict
from torch.utils.data import DataLoader, Dataset
from torch_geometric.data import HeteroData
from typing import Dict, List, Set, Tuple

from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.graph.builder import KnowledgeGraphBuilder
from app.ml.edge_filter import mask_target_edges, override_edge_index_dict
from app.ml.mlflow_tracker import MLflowTracker
from app.ml.models.hgt import NeuroDrugHGT
from app.ml.registry import ModelRegistry
from app.ml.trainer import HGTTrainer


# ── Feature extraction ──────────────────────────────────────────────────────
FEATURE_DIM = 16


def _pad(feats: List[float]) -> List[float]:
    if len(feats) >= FEATURE_DIM:
        return feats[:FEATURE_DIM]
    return feats + [0.0] * (FEATURE_DIM - len(feats))


# ── FIX-T1: unique one-hot per disease ──────────────────────────────────────
MONDO_TO_IDX: Dict[str, int] = {
    "MONDO_0018177": 0,   # Glioblastoma Multiforme
    "MONDO_0005072": 1,   # Neuroblastoma
    "MONDO_0012817": 2,   # Ewing Sarcoma
    "MONDO_0007959": 3,   # Medulloblastoma
    "MONDO_0019004": 4,   # Wilms Tumor
}
NAME_TO_IDX: Dict[str, int] = {
    "glioblastoma": 0,
    "neuroblastoma": 1,
    "ewing": 2,
    "medulloblastoma": 3,
    "wilms": 4,
}
N_DISEASES = len(MONDO_TO_IDX)

# Reverse lookup for readable per-disease reporting (feature-index space,
# NOT the same as the graph's Disease node index — see resolution below).
MONDO_TO_NAME: Dict[str, str] = {
    "MONDO_0018177": "Glioblastoma Multiforme",
    "MONDO_0005072": "Neuroblastoma",
    "MONDO_0012817": "Ewing Sarcoma",
    "MONDO_0007959": "Medulloblastoma",
    "MONDO_0019004": "Wilms Tumor",
}


def _disease_feats(attrs: dict) -> List[float]:
    """
    Return a 5-dim one-hot vector identifying which of the 5 target diseases
    this node represents, padded to FEATURE_DIM.

    Lookup strategy (in order):
      1. Search all attr values (including '_node_key') for MONDO IDs
      2. Name-based keyword match
      3. All-zeros fallback (unknown disease — shouldn't happen)
    """
    one_hot = [0.0] * N_DISEASES

    # Strategy 1: scan every string value in attrs for a MONDO ID
    # '_node_key' is injected by nx_to_heterodata (FIX-T2)
    searchable = " ".join(str(v) for v in attrs.values() if v is not None)
    for mondo_id, idx in MONDO_TO_IDX.items():
        if mondo_id in searchable:
            one_hot[idx] = 1.0
            return _pad(one_hot)

    # Strategy 2: name keyword
    name = (attrs.get("name") or "").lower()
    for keyword, idx in NAME_TO_IDX.items():
        if keyword in name:
            one_hot[idx] = 1.0
            return _pad(one_hot)

    logger.warning(f"_disease_feats: could not identify disease from attrs={attrs}")
    return _pad(one_hot)


def _gene_feats(attrs: dict) -> List[float]:
    f = attrs.get("features") or {}
    return _pad([
        float(f.get("is_oncogene") or 0),
        float(f.get("is_tumor_suppressor") or 0),
    ])


def _drug_feats(attrs: dict) -> List[float]:
    f = attrs.get("features") or {}
    try:
        max_phase = float(f.get("max_phase") or 0) / 4.0
    except (TypeError, ValueError):
        max_phase = 0.0
    return _pad([max_phase])


FEAT_FN = {
    "Gene":    _gene_feats,
    "Drug":    _drug_feats,
    "Disease": _disease_feats,
}


# ── nx.MultiDiGraph → PyG HeteroData ────────────────────────────────────────

def nx_to_heterodata(nx_graph) -> Tuple[HeteroData, Dict[str, List[str]]]:
    """
    Convert the NetworkX knowledge graph to a PyG HeteroData.

    FIX-T2: injects '_node_key' into the attrs dict passed to feature
    functions so _disease_feats can extract the MONDO ID from the node key
    (e.g. "Disease:MONDO_0018177") without needing a DB round-trip.
    """
    # ── group nodes by type ──────────────────────────────────────────────────
    node_lists: Dict[str, List[str]] = defaultdict(list)
    node_to_idx: Dict[str, Tuple[str, int]] = {}

    for node_key, attrs in nx_graph.nodes(data=True):
        ntype = attrs.get("node_type", "Unknown")
        idx = len(node_lists[ntype])
        node_lists[ntype].append(node_key)
        node_to_idx[node_key] = (ntype, idx)

    # ── feature matrices ─────────────────────────────────────────────────────
    data = HeteroData()
    for ntype, keys in node_lists.items():
        fn = FEAT_FN.get(ntype, lambda a: _pad([0.0]))
        # FIX-T2: inject node key so feature functions can use it for ID lookup
        feat_matrix = [fn({**nx_graph.nodes[k], "_node_key": str(k)}) for k in keys]
        data[ntype].x = torch.tensor(feat_matrix, dtype=torch.float)
        data[ntype].node_keys = keys

    # ── forward edges ─────────────────────────────────────────────────────────
    fwd_groups: Dict[Tuple, List[Tuple[int, int]]] = defaultdict(list)

    for src_key, dst_key, edge_attrs in nx_graph.edges(data=True):
        if src_key not in node_to_idx or dst_key not in node_to_idx:
            continue
        src_type, src_idx = node_to_idx[src_key]
        dst_type, dst_idx = node_to_idx[dst_key]
        rel = edge_attrs.get("edge_type") or "interacts"
        fwd_groups[(src_type, rel, dst_type)].append((src_idx, dst_idx))

    for (src_type, rel, dst_type), edges in fwd_groups.items():
        ei = torch.tensor(edges, dtype=torch.long).t().contiguous()
        data[src_type, rel, dst_type].edge_index = ei

    # ── reverse edges ─────────────────────────────────────────────────────────
    for (src_type, rel, dst_type) in list(fwd_groups.keys()):
        rev_rel = f"rev_{rel}"
        rev_triple = (dst_type, rev_rel, src_type)
        if rev_triple not in fwd_groups:
            rev_edges = [(d, s) for s, d in fwd_groups[(src_type, rel, dst_type)]]
            if rev_edges:
                ei = torch.tensor(rev_edges, dtype=torch.long).t().contiguous()
                data[dst_type, rev_rel, src_type].edge_index = ei

    return data, dict(node_lists)


# ── Link-prediction dataset ──────────────────────────────────────────────────

class Batch:
    __slots__ = ("x_dict", "edge_index_dict", "src_nodes", "dst_nodes",
                 "src_type", "dst_type", "labels")


class DrugDiseaseDataset(Dataset):
    """
    Static dataset: positives paired with a fixed, pre-sampled set of
    negatives. Used for val/test so evaluation metrics are reproducible
    across epochs (the negative set doesn't change run to run).
    """
    def __init__(
        self,
        data: HeteroData,
        pos_pairs: List[Tuple[int, int]],
        neg_pairs: List[Tuple[int, int]],
        batch_size: int = 64,
    ):
        self.data = data
        combined = (
            [(s, d, 1.0) for s, d in pos_pairs] +
            [(s, d, 0.0) for s, d in neg_pairs]
        )
        rng = np.random.default_rng(42)
        rng.shuffle(combined)
        self.pairs = combined
        self.bs = batch_size

    def __len__(self) -> int:
        return max(1, len(self.pairs) // self.bs)

    def __getitem__(self, idx: int) -> Batch:
        lo = idx * self.bs
        hi = min(lo + self.bs, len(self.pairs))
        chunk = self.pairs[lo:hi]

        b = Batch()
        b.x_dict          = {k: self.data[k].x         for k in self.data.node_types}
        b.edge_index_dict = {k: self.data[k].edge_index for k in self.data.edge_types}
        b.src_nodes       = torch.tensor([p[0] for p in chunk], dtype=torch.long)
        b.dst_nodes       = torch.tensor([p[1] for p in chunk], dtype=torch.long)
        b.src_type        = "Drug"
        b.dst_type        = "Disease"
        b.labels          = torch.tensor([p[2] for p in chunk], dtype=torch.float)
        return b


class DynamicNegSamplingDataset(Dataset):
    """
    Training dataset: only holds positive pairs. Every time a batch is
    fetched, a fresh set of negatives is sampled — one negative per positive
    edge in that batch (1:1 ratio) — by keeping the disease node fixed and
    pairing it with a randomly selected drug node that isn't a known
    positive for that disease (head/drug-side corruption). This means the
    model sees a different negative sample each epoch instead of a single
    static negative pool.

    FIX-D1 (train/eval task mismatch): negatives previously corrupted the
    DISEASE side (fix drug, swap in one of only 5 diseases) — that trains
    and AUC-evaluates the model on a trivial 1-in-5 task, which is why AUC
    looked great (~0.94) while real ranking performance (rank the true drug
    among ALL 2249 candidates for a disease — the actual repurposing task)
    was close to random. Corrupting the drug side instead makes training
    match the evaluation task, so AUC will drop, but it will now be an
    honest number for the thing the model is actually meant to do.
    """
    def __init__(
        self,
        data: HeteroData,
        pos_pairs: List[Tuple[int, int]],
        all_pos: Set[Tuple[int, int]],
        n_drug: int,
        batch_size: int = 64,
        seed: int = 42,
    ):
        self.data = data
        self.pos_pairs = pos_pairs
        self.all_pos = all_pos
        self.n_drug = n_drug
        self.bs = max(1, batch_size // 2)  # half the batch is positives, half negatives
        self.rng = np.random.default_rng(seed)

    def __len__(self) -> int:
        return max(1, len(self.pos_pairs) // self.bs)

    def __getitem__(self, idx: int) -> Batch:
        lo = idx * self.bs
        hi = min(lo + self.bs, len(self.pos_pairs))
        pos_chunk = self.pos_pairs[lo:hi]
        neg_chunk = sample_negatives(pos_chunk, self.all_pos, self.n_drug, self.rng)

        combined = (
            [(s, d, 1.0) for s, d in pos_chunk] +
            [(s, d, 0.0) for s, d in neg_chunk]
        )
        self.rng.shuffle(combined)

        b = Batch()
        b.x_dict          = {k: self.data[k].x         for k in self.data.node_types}
        b.edge_index_dict = {k: self.data[k].edge_index for k in self.data.edge_types}
        b.src_nodes       = torch.tensor([p[0] for p in combined], dtype=torch.long)
        b.dst_nodes       = torch.tensor([p[1] for p in combined], dtype=torch.long)
        b.src_type        = "Drug"
        b.dst_type        = "Disease"
        b.labels          = torch.tensor([p[2] for p in combined], dtype=torch.float)
        return b


# Independent seeds per split so that sample_negatives(<split>, ...) returns
# the same negatives regardless of which other splits are sampled before or
# after it, or in what order — see FIX-D2 below. run_baselines.py imports
# these directly rather than redefining them, so the two scripts can never
# drift apart again.
SPLIT_SEED_TRAIN = 41
SPLIT_SEED_VAL = 43
SPLIT_SEED_TEST = 47


def build_splits(
    data: HeteroData,
    n_drug: int,
    n_disease: int,
    train_frac: float = 0.7,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
    seed: int = 42,
) -> Tuple[List, List, List, Set[Tuple[int, int]]]:
    """
    Randomly split the positive Drug-Disease edges into 70% train / 15% val /
    15% test (default fractions). Negatives are NOT pre-generated here —
    they're sampled fresh per split (see `sample_negatives`) so that training
    can draw a new random negative set every batch/epoch instead of reusing
    one static pool.

    Returns (train_pos, val_pos, test_pos, all_pos_set).
    """
    assert abs((train_frac + val_frac + test_frac) - 1.0) < 1e-6, \
        "train_frac + val_frac + test_frac must sum to 1.0"

    pos: Set[Tuple[int, int]] = set()

    for (src_type, rel, dst_type) in data.edge_types:
        if src_type == "Drug" and dst_type == "Disease":
            ei = data[src_type, rel, dst_type].edge_index
            for i in range(ei.size(1)):
                pos.add((int(ei[0, i]), int(ei[1, i])))

    logger.info(f"Positive Drug-Disease pairs: {len(pos)}")

    if not pos:
        raise RuntimeError(
            "No Drug-Disease edges in the graph.\n"
            "Run ChEMBL and OpenTargets ETL before training:\n"
            "  docker-compose exec api python -m app.services.etl.chembl\n"
            "  docker-compose exec api python -m app.services.etl.opentargets"
        )

    rng = np.random.default_rng(seed)
    pos_list = sorted(pos)
    rng.shuffle(pos_list)

    n = len(pos_list)
    n_train = int(n * train_frac)
    n_val = int(n * val_frac)
    # remainder goes to test so the three splits always add up to n
    train_pos = pos_list[:n_train]
    val_pos = pos_list[n_train:n_train + n_val]
    test_pos = pos_list[n_train + n_val:]

    logger.info(
        f"Split (70/15/15): train={len(train_pos)}, val={len(val_pos)}, test={len(test_pos)}"
    )

    return train_pos, val_pos, test_pos, pos


def sample_negatives(
    pos_pairs: List[Tuple[int, int]],
    all_pos: Set[Tuple[int, int]],
    n_drug: int,
    rng: np.random.Generator,
    max_tries: int = 20,
) -> List[Tuple[int, int]]:
    """
    For each positive (drug, disease) edge, sample one negative by keeping the
    disease node fixed and pairing it with a randomly selected drug node that
    is NOT a known positive for that disease (head/drug-side corruption).
    This gives an equal (1:1) number of negatives to positives.

    FIX-D1: this used to corrupt the disease side (fix drug, swap in one of
    only 5 diseases), which trained/evaluated the model on a trivial 1-in-5
    task instead of the real repurposing task — ranking the true drug among
    ALL n_drug candidates for a given disease. Corrupting the drug side here
    makes the negative-sampling distribution match `evaluate_ranking_per_
    disease` in app/ml/trainer.py, so training and evaluation are finally
    testing the same thing.
    """
    negatives: List[Tuple[int, int]] = []
    for _, disease in pos_pairs:
        for _ in range(max_tries):
            d = int(rng.integers(0, n_drug))
            if (d, disease) not in all_pos:
                negatives.append((d, disease))
                break
        else:
            # extremely unlikely with a sparse graph, but fall back to any
            # valid negative rather than dropping the sample
            d = int(rng.integers(0, n_drug))
            negatives.append((d, disease))
    return negatives


# ── Main ─────────────────────────────────────────────────────────────────────

async def main(batch_size: int = 4096, max_epochs: int = 100, patience: int = 15, min_epochs: int = 0) -> None:

    # ── 1. Load real graph from PostgreSQL ───────────────────────────────────
    logger.info("Connecting to database …")
    async with AsyncSessionLocal() as session:
        builder  = KnowledgeGraphBuilder(session)
        nx_graph = await builder.build_from_database()

    n_nodes = nx_graph.number_of_nodes()
    n_edges = nx_graph.number_of_edges()
    logger.info(f"Loaded graph: {n_nodes} nodes, {n_edges} edges")

    if n_nodes == 0:
        raise RuntimeError(
            "Empty knowledge graph — run seed_initial_data.py and ETL pipelines first."
        )

    # ── 2. Convert to PyG HeteroData ─────────────────────────────────────────
    logger.info("Converting to PyG HeteroData …")
    data, node_lists = nx_to_heterodata(nx_graph)

    n_gene    = data["Gene"].x.size(0)    if "Gene"    in data.node_types else 0
    n_drug    = data["Drug"].x.size(0)    if "Drug"    in data.node_types else 0
    n_disease = data["Disease"].x.size(0) if "Disease" in data.node_types else 0

    logger.info(f"Node counts — Gene: {n_gene}, Drug: {n_drug}, Disease: {n_disease}")
    logger.info(f"Edge types  — {[str(et) for et in data.edge_types]}")

    # ── Sanity check: verify disease features are unique ─────────────────────
    disease_feats = data["Disease"].x
    unique_rows = len(set(tuple(r.tolist()) for r in disease_feats))
    logger.info(
        f"Disease feature sanity: {n_disease} nodes, {unique_rows} unique feature vectors"
        f" {'✓ OK' if unique_rows == n_disease else '✗ WARN: some diseases have identical features'}"
    )

    if n_drug == 0 or n_disease == 0:
        raise RuntimeError("No Drug or Disease nodes in graph — run ETL first.")

    # ── 3. Build train / val / test datasets (70/15/15) ─────────────────────
    train_pos, val_pos, test_pos, all_pos = build_splits(data, n_drug, n_disease)

    # FIX-D2 (val/test negative mismatch across scripts): run_training.py and
    # run_baselines.py both used a single np.random.default_rng(42) stream for
    # negatives, but called sample_negatives() in a different order per split
    # (val-then-test here vs train-then-val there). A Generator's output
    # depends on how many draws already happened, not just its seed, so "val
    # negatives" silently differed between the two scripts even though both
    # said seed=42 — this alone is enough to move val AUC by several points,
    # because the two scripts were scoring HGT against two different negative
    # sets while calling it the same "val" metric. Giving each split its own
    # independently-seeded generator makes a given split's negatives identical
    # no matter what else is sampled before or after it, in any script.
    val_neg = sample_negatives(val_pos, all_pos, n_drug, np.random.default_rng(SPLIT_SEED_VAL))
    test_neg = sample_negatives(test_pos, all_pos, n_drug, np.random.default_rng(SPLIT_SEED_TEST))

    # FIX-L1 (transductive leakage): nx_to_heterodata puts every Drug-Disease
    # edge — train, val, AND test — into the graph used for message passing,
    # so a Disease node could see the exact edge it's being evaluated on.
    # Mask BOTH the val- and test-split positives out of the message-passing
    # graph for every loader, so the model only ever aggregates over the
    # training subgraph (standard transductive link-prediction setup,
    # matches PyG's RandomLinkSplit). See app/ml/edge_filter.py for details.
    full_edge_index_dict = {k: data[k].edge_index for k in data.edge_types}
    masked_edge_index_dict = mask_target_edges(
        full_edge_index_dict, exclude_pairs=list(val_pos) + list(test_pos)
    )
    logger.info(
        f"Leakage guard: masked {sum(ei.size(1) for k, ei in full_edge_index_dict.items()) - sum(ei.size(1) for k, ei in masked_edge_index_dict.items())} "
        f"val/test-positive edge instances out of the message-passing graph."
    )

    # Train: negatives are resampled fresh for every batch (1:1 with
    # positives) — see DynamicNegSamplingDataset docstring.
    train_ds = DynamicNegSamplingDataset(
        data, train_pos, all_pos, n_drug, batch_size=batch_size
    )
    val_ds  = DrugDiseaseDataset(data, val_pos,  val_neg,  batch_size=batch_size)
    test_ds = DrugDiseaseDataset(data, test_pos, test_neg, batch_size=batch_size)
    override_edge_index_dict(train_ds, masked_edge_index_dict)
    override_edge_index_dict(val_ds, masked_edge_index_dict)
    override_edge_index_dict(test_ds, masked_edge_index_dict)

    train_loader = DataLoader(train_ds, batch_size=1, collate_fn=lambda x: x[0])
    val_loader   = DataLoader(val_ds,   batch_size=1, collate_fn=lambda x: x[0])
    test_loader  = DataLoader(test_ds,  batch_size=1, collate_fn=lambda x: x[0])

    # PERFORMANCE NOTE: every batch re-runs the full 3-layer HGT encoder over
    # the WHOLE graph (all 2820+ nodes) just to score `batch_size` pairs — the
    # graph itself doesn't change within an epoch, only the weights do after
    # each step. Fewer, bigger batches means fewer redundant full-graph
    # passes per epoch. batch_size=4096 (default) exceeds the training set
    # size, so this becomes single full-batch gradient descent: exactly 1
    # encoder pass per epoch instead of ~37 at the old batch_size=64.
    logger.info(
        f"Train batches/epoch: {len(train_ds)}, Val batches/epoch: {len(val_ds)}, "
        f"Test batches: {len(test_ds)} (batch_size={batch_size})"
    )

    # ── 4. Build model ────────────────────────────────────────────────────────
    params = dict(
        hidden_channels=128,
        num_layers=2,
        num_heads=4,
        lr=3e-4,
        weight_decay=1e-5,
        max_epochs=max_epochs,
        patience=patience,
        min_epochs=min_epochs,
        grad_clip=1.0,
        scheduler="cosine_annealing",
        scheduler_eta_min=1e-5,
    )

    model = NeuroDrugHGT(
        metadata=data.metadata(),
        hidden_channels=params["hidden_channels"],
        num_layers=params["num_layers"],
        num_heads=params["num_heads"],
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Training on {device.upper()}")

    # FIX-T3: pass metadata so it's saved with each checkpoint
    trainer = HGTTrainer(
        model,
        device=device,
        lr=params["lr"],
        weight_decay=params["weight_decay"],
        max_epochs=params["max_epochs"],
        patience=params["patience"],
        min_epochs=params["min_epochs"],
        grad_clip=params["grad_clip"],
        metadata=data.metadata(),
    )

    # ── 5. Train with MLflow tracking ─────────────────────────────────────────
    tracker = MLflowTracker(experiment_name="neurodrug_hgt_real")
    tracker.start_run(run_name="hgt_real_graph_v2", params=params)

    trainer.fit(train_loader, val_loader)

    for entry in trainer.history:
        tracker.log_metrics(
            {k.replace("@", "_at_"): v for k, v in entry.items() if k != "epoch"},
            step=entry["epoch"],
        )

    # ── 5b. Final evaluation on the held-out test split ──────────────────────
    # Reload the best (highest val AUC) checkpoint before scoring test, so the
    # reported test metrics reflect the early-stopped model, not whatever
    # epoch happened to run last.
    trainer.load_checkpoint("best_model.pt")
    test_metrics = trainer.evaluate(test_loader)
    logger.info(
        f"Test metrics — classification (roc_auc / average_precision only "
        f"are meaningful here; hits@k/mrr/ndcg@k below are flat-batch "
        f"artifacts, see per-disease ranking eval): {test_metrics}"
    )

    # Proper per-disease filtered ranking eval (tail corruption): for each
    # disease, score ALL drugs against it, filter out other known positives,
    # rank the true test drug. Overwrites the flat hits@k/mrr/ndcg@k above,
    # which were capped at k/n_pos and not real ranking metrics.
    disease_node_keys = data["Disease"].node_keys if "Disease" in data.node_types else []

    def _disease_name(idx: int) -> str:
        key = str(disease_node_keys[idx]) if idx < len(disease_node_keys) else ""
        for mondo_id, name in MONDO_TO_NAME.items():
            if mondo_id in key:
                return name
        return key or f"disease_{idx}"

    macro_ranking, per_disease_ranking = trainer.evaluate_ranking_per_disease(
        data, masked_edge_index_dict, test_pos, all_pos, n_drug
    )

    logger.info("Per-disease filtered ranking metrics (test split):")
    for disease_idx, m, n_edges in per_disease_ranking:
        logger.info(
            f"  {_disease_name(disease_idx):28s} (n_test_edges={n_edges:3d}) — "
            f"MRR: {m['mrr']:.4f}  Hits@10: {m['hits@10']:.4f}  "
            f"Hits@20: {m['hits@20']:.4f}  NDCG@10: {m['ndcg@10']:.4f}"
        )
    logger.info(f"Macro-averaged across diseases: {macro_ranking}")

    # roc_auc / average_precision are legitimate as computed (flat binary
    # classification over pos+neg test pairs); hits@k/mrr/ndcg@k are
    # replaced with the macro-averaged per-disease ranking versions.
    test_metrics = {
        "roc_auc": test_metrics["roc_auc"],
        "average_precision": test_metrics["average_precision"],
        **macro_ranking,
    }
    logger.info(f"Test metrics (final, corrected): {test_metrics}")

    tracker.log_metrics(
        {f"test_{k.replace('@', '_at_')}": v for k, v in test_metrics.items()},
        step=trainer.history[-1]["epoch"] + 1,
    )

    import mlflow
    mlflow.log_artifact("checkpoints/best_model.pt", artifact_path="hgt_model")

    # ── 6. Register checkpoint ────────────────────────────────────────────────
    registry = ModelRegistry()
    registry.register(
        name="NeuroDrugHGT",
        version="2.0.0",
        architecture="HGT",
        checkpoint_path="checkpoints/best_model.pt",
        hyperparameters=params,
        metrics={**trainer.history[-1], **{f"test_{k}": v for k, v in test_metrics.items()}},
        is_production=True,
    )

    tracker.end_run()
    logger.info(
        f"Training complete. Best val AUC: {trainer.best_val_auc:.4f}. "
        f"Test AUC: {test_metrics.get('roc_auc', float('nan')):.4f}. "
        "Results at http://localhost:5000"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train NeuroDrug's HGT link predictor on the real knowledge graph.")
    parser.add_argument(
        "--batch-size", type=int, default=4096,
        help="Pairs per mini-batch. Every batch re-runs the full graph encoder, so bigger = fewer "
             "redundant full-graph passes per epoch = faster on CPU. Default 4096 exceeds the "
             "training set size (~2400 pairs), giving 1 full-batch pass/epoch. Use a smaller value "
             "(e.g. 64) only if you specifically want mini-batch SGD noise/regularization and have "
             "the GPU/CPU time to spare.",
    )
    parser.add_argument(
        "--epochs", type=int, default=200,
        help="Max epochs (default: 200, matches the cosine annealing scheduler's T_max).",
    )
    parser.add_argument(
        "--patience", type=int, default=25,
        help="Early-stopping patience on validation AUC (default: 25 epochs).",
    )
    parser.add_argument(
        "--min-epochs", type=int, default=50,
        help="Floor on epochs before early stopping is allowed to trigger, regardless of "
             "patience (default: 50). Previously the model could stop as early as epoch "
             "8 + patience with no way to force a longer run — this guarantees at least "
             "this many epochs of training every time.",
    )
    args = parser.parse_args()
    asyncio.run(main(
        batch_size=args.batch_size,
        max_epochs=args.epochs,
        patience=args.patience,
        min_epochs=args.min_epochs,
    ))
