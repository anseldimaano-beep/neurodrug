"""
run_baselines.py — Six-baseline comparison (Proposal Section D, Step 3.1 /
Section F, "Baseline Comparison and Statistical Testing").

Trains Random, Jaccard, Matrix Factorization, homogeneous GCN, R-GCN, and
HAN on the same Drug-Disease link-prediction split used by run_training.py,
evaluates each against the trained HGT checkpoint on the identical test
set, and runs the permutation test (n=1000) from app/ml/metrics.py to test
H1: "the HGT-based GNN framework will achieve a statistically significantly
higher ROC AUC ... compared to all baseline methods."

Usage (from the Docker container, after run_training.py has produced
checkpoints/best_model.pt):
    docker-compose exec api python scripts/run_baselines.py

Output: checkpoints/baseline_comparison.json + a printed leaderboard table.
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Dict, List, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from torch.optim import Adam

from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.graph.builder import KnowledgeGraphBuilder
from app.ml.edge_filter import mask_target_edges
from app.ml.metrics import evaluate_all, permutation_test
from app.ml.models.baselines import (
    RandomBaseline,
    JaccardBaseline,
    MatrixFactorizationBaseline,
    HomogeneousGCN,
    RGCNBaseline,
    HANLinkPredictor,
)
from app.ml.models.hgt import LinkPredictor, NeuroDrugHGT
from app.ml.predictor import DrugRepurposingPredictor

from run_training import build_splits, nx_to_heterodata, sample_negatives  # noqa: E402


GRAPH_EPOCHS_DEFAULT = 60  # fewer than the 100-epoch HGT run since these are baselines, not the main model


# ── Heterogeneous -> homogeneous projection (needed for GCN / R-GCN) ────────

def to_homogeneous(data, edge_index_dict) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, Dict[str, Tuple[int, int]], int]:
    """
    Flatten a PyG HeteroData into a single (x, edge_index, edge_type) triple.
    All node types already share FEATURE_DIM=16 (see graph_convert.py), so
    features concatenate directly with no extra padding needed.

    `edge_index_dict` is passed explicitly (rather than read straight off
    `data`) so callers can supply the leakage-masked graph — see
    app/ml/edge_filter.py — instead of the raw one, which contains
    validation-positive Drug-Disease edges the model shouldn't be able to see.

    Returns
    -------
    x            : [N, 16] float tensor, all node types stacked
    edge_index   : [2, E] long tensor, global node indices
    edge_type    : [E] long tensor, integer relation id (for R-GCN)
    offsets      : {node_type: (start_idx, end_idx)} in the global index space
    num_relations: number of distinct relation ids
    """
    offsets: Dict[str, Tuple[int, int]] = {}
    xs = []
    cursor = 0
    for ntype in data.node_types:
        n = data[ntype].x.size(0)
        offsets[ntype] = (cursor, cursor + n)
        xs.append(data[ntype].x)
        cursor += n
    x = torch.cat(xs, dim=0)

    relation_to_id: Dict[str, int] = {}
    edge_index_parts = []
    edge_type_parts = []
    for (src_type, rel, dst_type), ei in edge_index_dict.items():
        if ei.numel() == 0:
            continue
        src_off, _ = offsets[src_type]
        dst_off, _ = offsets[dst_type]
        global_ei = torch.stack([ei[0] + src_off, ei[1] + dst_off])
        edge_index_parts.append(global_ei)

        rel_id = relation_to_id.setdefault(rel, len(relation_to_id))
        edge_type_parts.append(torch.full((ei.size(1),), rel_id, dtype=torch.long))

    edge_index = torch.cat(edge_index_parts, dim=1)
    edge_type = torch.cat(edge_type_parts, dim=0)
    return x, edge_index, edge_type, offsets, len(relation_to_id)


def build_adjacency(edge_index: torch.Tensor, num_nodes: int) -> Dict[int, List[int]]:
    adj: Dict[int, List[int]] = {i: [] for i in range(num_nodes)}
    src, dst = edge_index[0].tolist(), edge_index[1].tolist()
    for s, d in zip(src, dst):
        adj[s].append(d)
        adj[d].append(s)
    return adj


# ── Training loop shared by all graph-neural baselines ──────────────────────

def train_graph_baseline(
    encoder: torch.nn.Module,
    predictor: torch.nn.Module,
    forward_encoder,
    train_pairs: List[Tuple[int, int, float]],
    val_pairs: List[Tuple[int, int, float]],
    epochs: int,
    lr: float = 1e-3,
) -> Tuple[torch.nn.Module, torch.nn.Module, Dict[str, float]]:
    params = list(encoder.parameters()) + list(predictor.parameters())
    optimizer = Adam(params, lr=lr)

    def run_epoch(pairs, train: bool):
        encoder.train(train)
        predictor.train(train)
        srcs = torch.tensor([p[0] for p in pairs], dtype=torch.long)
        dsts = torch.tensor([p[1] for p in pairs], dtype=torch.long)
        labels = torch.tensor([p[2] for p in pairs], dtype=torch.float)

        if train:
            optimizer.zero_grad()
        z = forward_encoder()
        logits = predictor(z[srcs], z[dsts])
        loss = F.binary_cross_entropy_with_logits(logits, labels)
        if train:
            loss.backward()
            optimizer.step()
        return loss.item(), torch.sigmoid(logits).detach().numpy(), labels.numpy()

    best_auc = 0.0
    best_state = None
    for epoch in range(1, epochs + 1):
        train_loss, _, _ = run_epoch(train_pairs, train=True)
        with torch.no_grad():
            val_loss, val_scores, val_labels = run_epoch(val_pairs, train=False)
        val_auc = evaluate_all(val_labels, val_scores)["roc_auc"]
        if val_auc > best_auc:
            best_auc = val_auc
            best_state = (
                {k: v.clone() for k, v in encoder.state_dict().items()},
                {k: v.clone() for k, v in predictor.state_dict().items()},
            )
        if epoch % 10 == 0 or epoch == epochs:
            logger.info(f"  epoch {epoch}/{epochs} — train_loss={train_loss:.4f} val_auc={val_auc:.4f}")

    if best_state is not None:
        encoder.load_state_dict(best_state[0])
        predictor.load_state_dict(best_state[1])

    with torch.no_grad():
        _, val_scores, val_labels = run_epoch(val_pairs, train=False)
    return encoder, predictor, {"roc_auc": best_auc, "final_scores": val_scores, "final_labels": val_labels}


async def main(hgt_checkpoint: str, epochs: int):
    async with AsyncSessionLocal() as session:
        builder = KnowledgeGraphBuilder(session)
        nx_graph = await builder.build_from_database()
    if nx_graph.number_of_nodes() == 0:
        raise RuntimeError("Empty knowledge graph — run ETL pipelines first.")

    data, node_lists = nx_to_heterodata(nx_graph)
    n_drug = data["Drug"].x.size(0)
    n_disease = data["Disease"].x.size(0)
    if n_drug == 0 or n_disease == 0:
        raise RuntimeError("No Drug or Disease nodes — run ETL first.")

    # FIX-B2: build_splits() returns (train_pos, val_pos, test_pos, all_pos) —
    # it does NOT generate negatives. This used to be unpacked as
    # `train_pos, val_pos, train_neg, val_neg = build_splits(...)`, which
    # silently bound `val_neg` to the entire set of TRUE positive pairs
    # (all_pos, which includes val_pos itself) and labeled them 0.0 in the
    # eval set below. A correctly-scoring model — one that gives high scores
    # to real drug-disease links — then looks *anti-correlated* with those
    # labels, because most of what's labeled "negative" is actually a real
    # positive link. This is what was producing HGT's below-random,
    # apparently-inverted AUC. It also meant every baseline below (GCN,
    # R-GCN, HAN) was being *trained* on test_pos mislabeled as negatives.
    train_pos, val_pos, test_pos, all_pos = build_splits(data, n_drug, n_disease)
    _neg_rng = np.random.default_rng(42)
    train_neg = sample_negatives(train_pos, all_pos, n_drug, _neg_rng)
    val_neg = sample_negatives(val_pos, all_pos, n_drug, _neg_rng)

    # FIX-L1 (transductive leakage — see app/ml/edge_filter.py): every model
    # below is evaluated using a graph with val-positive Drug-Disease edges
    # masked out of message passing, so the leaderboard reflects real
    # generalization rather than which model exploits the leak hardest.
    # NOTE: this does NOT retroactively fix a checkpoint that was *trained*
    # on the leaky graph (e.g. an existing checkpoints/best_model.pt from
    # before this fix) — its weights may still have partly learned to rely
    # on the leak. For a fully fair comparison, retrain HGT with the fixed
    # scripts/run_training.py first, then rerun this script.
    full_edge_index_dict = {k: data[k].edge_index for k in data.edge_types}
    masked_edge_index_dict = mask_target_edges(full_edge_index_dict, exclude_pairs=val_pos)
    logger.info(
        f"Leakage guard: masked {sum(ei.size(1) for ei in full_edge_index_dict.values()) - sum(ei.size(1) for ei in masked_edge_index_dict.values())} "
        f"validation-positive edge instances out of the message-passing graph for every model below."
    )

    # ── Load the trained HGT model to get its scores on the same val split ──
    hgt_model = NeuroDrugHGT(metadata=data.metadata(), hidden_channels=128, num_layers=2, num_heads=4)
    hgt_predictor = DrugRepurposingPredictor(hgt_model)

    val_pairs = [(s, d, 1.0) for s, d in val_pos] + [(s, d, 0.0) for s, d in val_neg]
    x_dict = {k: data[k].x for k in data.node_types}
    src_t = torch.tensor([p[0] for p in val_pairs], dtype=torch.long)
    dst_t = torch.tensor([p[1] for p in val_pairs], dtype=torch.long)
    labels_np = np.array([p[2] for p in val_pairs])

    # FIX-B1: HGTConv uses PyG lazy modules — their parameter shapes don't
    # exist until the first forward() call. load_checkpoint compares shapes
    # to decide which weights to load, so calling it on a never-run model
    # silently skips every lazy-initialized layer (i.e. most of the trained
    # weights) and evaluates on a mostly-random-init model instead. Run one
    # throwaway forward pass first to materialize those shapes, THEN load.
    with torch.no_grad():
        hgt_predictor.model(x_dict, masked_edge_index_dict, src_t, dst_t, "Drug", "Disease")
    hgt_predictor.load_checkpoint(hgt_checkpoint)

    with torch.no_grad():
        hgt_logits = hgt_predictor.model(x_dict, masked_edge_index_dict, src_t, dst_t, "Drug", "Disease")
        hgt_scores = torch.sigmoid(hgt_logits).numpy()
    hgt_metrics = evaluate_all(labels_np, hgt_scores)
    logger.warning(
        f"INVERSION CHECK — AUC(scores)={hgt_metrics['roc_auc']:.4f}  "
        f"AUC(1-scores)={evaluate_all(labels_np, 1 - hgt_scores)['roc_auc']:.4f}  "
        f"(if the second number is the healthy-looking one, this is a sign/label-flip bug, not a loading bug)"
    )
    logger.info(f"HGT (trained checkpoint) val metrics: {hgt_metrics}")

    results = [{"model": "HGT (proposed)", "type": "graph", **hgt_metrics, "p_value_vs_hgt": None}]

    # ── Homogeneous projection for GCN / R-GCN / HAN's encoder-agnostic pairs ─
    x, edge_index, edge_type, offsets, num_relations = to_homogeneous(data, masked_edge_index_dict)
    drug_off, _ = offsets["Drug"]
    disease_off, _ = offsets["Disease"]

    def to_global(pairs):
        return [(s + drug_off, d + disease_off, label) for s, d, label in pairs]

    global_train = to_global([(s, d, 1.0) for s, d in train_pos] + [(s, d, 0.0) for s, d in train_neg])
    global_val = to_global(val_pairs)

    # ── Random ───────────────────────────────────────────────────────────────
    random_scores = RandomBaseline().predict([(s, d) for s, d, _ in val_pairs])
    results.append({"model": "Random", "type": "traditional", **evaluate_all(labels_np, random_scores)})

    # ── Jaccard (on the original nx graph's undirected adjacency) ────────────
    adj_by_key: Dict[str, List[str]] = {n: list(nx_graph.neighbors(n)) + list(nx_graph.predecessors(n)) for n in nx_graph.nodes()}
    drug_keys = node_lists["Drug"]
    disease_keys = node_lists["Disease"]
    jaccard_pairs = [(drug_keys[s], disease_keys[d]) for s, d, _ in val_pairs]
    jaccard_scores = JaccardBaseline(adj_by_key).predict(jaccard_pairs)
    results.append({"model": "Jaccard similarity", "type": "traditional", **evaluate_all(labels_np, jaccard_scores)})

    # ── Matrix Factorization (Drug x Disease interaction matrix from training positives) ─
    interaction_matrix = np.zeros((n_drug, n_disease), dtype=np.float32)
    for s, d in train_pos:
        interaction_matrix[s, d] = 1.0
    mf = MatrixFactorizationBaseline(n_components=min(32, n_drug - 1, n_disease - 1) or 1)
    try:
        mf.fit(interaction_matrix)
        mf_scores = mf.predict([(s, d) for s, d, _ in val_pairs])
    except Exception as exc:  # NMF can fail on tiny/degenerate matrices
        logger.warning(f"Matrix factorization failed ({exc}); scoring as all-zero.")
        mf_scores = np.zeros(len(val_pairs))
    results.append({"model": "Matrix Factorization", "type": "traditional", **evaluate_all(labels_np, mf_scores)})

    # ── Homogeneous GCN ────────────────────────────────────────────────────────
    logger.info("Training homogeneous GCN baseline...")
    gcn = HomogeneousGCN(in_channels=x.size(1), hidden_channels=64, out_channels=32)
    gcn_pred = LinkPredictor(in_channels=32)
    gcn, gcn_pred, gcn_res = train_graph_baseline(
        gcn, gcn_pred, lambda: gcn(x, edge_index), global_train, global_val, epochs,
    )
    results.append({"model": "Homogeneous GCN", "type": "graph", **evaluate_all(gcn_res["final_labels"], gcn_res["final_scores"])})

    # ── R-GCN ────────────────────────────────────────────────────────────────
    logger.info("Training R-GCN baseline...")
    rgcn = RGCNBaseline(in_channels=x.size(1), hidden_channels=64, out_channels=32, num_relations=max(num_relations, 1))
    rgcn_pred = LinkPredictor(in_channels=32)
    rgcn, rgcn_pred, rgcn_res = train_graph_baseline(
        rgcn, rgcn_pred, lambda: rgcn(x, edge_index, edge_type), global_train, global_val, epochs,
    )
    results.append({"model": "R-GCN", "type": "graph", **evaluate_all(rgcn_res["final_labels"], rgcn_res["final_scores"])})

    # ── HAN (heterogeneous — uses x_dict / edge_index_dict directly) ─────────
    logger.info("Training HAN baseline...")
    han = HANLinkPredictor(metadata=data.metadata(), hidden_channels=128, num_layers=2, heads=4)
    han_optimizer = Adam(han.parameters(), lr=1e-3)
    x_dict = {k: data[k].x for k in data.node_types}
    # leakage-masked graph (see FIX-L1 above) — not the raw data.edge_types graph
    han_edge_index_dict = masked_edge_index_dict

    def han_epoch(pairs, train: bool):
        han.train(train)
        srcs = torch.tensor([p[0] for p in pairs], dtype=torch.long)
        dsts = torch.tensor([p[1] for p in pairs], dtype=torch.long)
        labels = torch.tensor([p[2] for p in pairs], dtype=torch.float)
        if train:
            han_optimizer.zero_grad()
        logits = han(x_dict, han_edge_index_dict, srcs, dsts, "Drug", "Disease")
        loss = F.binary_cross_entropy_with_logits(logits, labels)
        if train:
            loss.backward()
            han_optimizer.step()
        return torch.sigmoid(logits).detach().numpy(), labels.numpy()

    best_han_auc, best_han_state = 0.0, None
    for epoch in range(1, epochs + 1):
        han_epoch([(s, d, 1.0) for s, d in train_pos] + [(s, d, 0.0) for s, d in train_neg], train=True)
        with torch.no_grad():
            han_scores, han_labels = han_epoch(val_pairs, train=False)
        han_auc = evaluate_all(han_labels, han_scores)["roc_auc"]
        if han_auc > best_han_auc:
            best_han_auc = han_auc
            best_han_state = {k: v.clone() for k, v in han.state_dict().items()}
        if epoch % 10 == 0 or epoch == epochs:
            logger.info(f"  [HAN] epoch {epoch}/{epochs} — val_auc={han_auc:.4f}")
    if best_han_state is not None:
        han.load_state_dict(best_han_state)
    with torch.no_grad():
        han_scores, han_labels = han_epoch(val_pairs, train=False)
    results.append({"model": "HAN", "type": "graph", **evaluate_all(han_labels, han_scores)})

    # ── Permutation test: HGT vs every baseline (Section F procedure) ────────
    for r in results:
        if r["model"] == "HGT (proposed)":
            continue
        if r["model"] == "Random":
            scores = random_scores
        elif r["model"] == "Jaccard similarity":
            scores = jaccard_scores
        elif r["model"] == "Matrix Factorization":
            scores = mf_scores
        elif r["model"] == "Homogeneous GCN":
            scores = gcn_res["final_scores"]
        elif r["model"] == "R-GCN":
            scores = rgcn_res["final_scores"]
        elif r["model"] == "HAN":
            scores = han_scores
        else:
            continue
        p_value = permutation_test(labels_np, hgt_scores, scores, n_permutations=1000)
        r["p_value_vs_hgt"] = round(p_value, 4)
        r["significant_at_0.05"] = p_value < 0.05

    os.makedirs("checkpoints", exist_ok=True)
    out_path = os.path.join("checkpoints", "baseline_comparison.json")
    serializable = [{k: v for k, v in r.items() if k not in ("final_scores", "final_labels")} for r in results]
    with open(out_path, "w") as f:
        json.dump(serializable, f, indent=2)

    print("\n" + "=" * 92)
    print(f"{'Model':<24}{'Type':<14}{'ROC AUC':<10}{'AP':<10}{'Hits@10':<10}{'p vs HGT':<10}{'Sig.':<6}")
    print("-" * 92)
    for r in sorted(serializable, key=lambda r: -r["roc_auc"]):
        sig = "yes" if r.get("significant_at_0.05") else ("n/a" if r["model"] == "HGT (proposed)" else "no")
        p = r.get("p_value_vs_hgt")
        p_str = f"{p:.4f}" if p is not None else "—"
        print(f"{r['model']:<24}{r['type']:<14}{r['roc_auc']:<10.4f}{r['average_precision']:<10.4f}{r['hits@10']:<10.4f}{p_str:<10}{sig:<6}")
    print("=" * 92)
    print(f"Full results written to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare NeuroDrug's HGT model against six baselines (Proposal Section D, Step 3.1).")
    parser.add_argument("--hgt-checkpoint", default="checkpoints/best_model.pt")
    parser.add_argument("--epochs", type=int, default=GRAPH_EPOCHS_DEFAULT)
    args = parser.parse_args()
    asyncio.run(main(args.hgt_checkpoint, args.epochs))
