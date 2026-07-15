"""
generate_tsne.py — Drug embedding t-SNE visualization (Proposal Section D,
Step 3.4 / Section F, "Embedding Quality Analysis").

Loads the trained NeuroDrugHGT checkpoint and the real knowledge graph,
runs the encoder once to get 128-dim Drug node embeddings, projects them
to 2D with t-SNE, colors points by a coarse mechanism-of-action (MoA)
class parsed from Drug.mechanism_of_action, and saves a publication-style
scatter plot.

Usage (from the Docker container):
    docker-compose exec api python scripts/generate_tsne.py
    docker-compose exec api python scripts/generate_tsne.py --checkpoint checkpoints/best_model.pt --out checkpoints/drug_tsne.png

Output:
    checkpoints/drug_tsne.png        — the plot
    checkpoints/drug_tsne_coords.json — raw 2D coords + labels, for reuse
                                        in the frontend Evidence/Training tabs
"""

import argparse
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Dict, List

import matplotlib
matplotlib.use("Agg")  # headless — no display in the Docker container
import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.manifold import TSNE
from sqlalchemy import select

from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.graph.builder import KnowledgeGraphBuilder
from app.ml.models.hgt import NeuroDrugHGT
from app.ml.predictor import DrugRepurposingPredictor
from app.models.domain import Drug

from run_training import nx_to_heterodata  # noqa: E402


# ── Mechanism-of-action keyword buckets ──────────────────────────────────────
# Matches the proposal's Step 3.4 categories. Applied to Drug.mechanism_of_action
# (free text from ChEMBL) via simple keyword search — good enough for a
# qualitative embedding-quality plot, not a clinical classification.
_MOA_KEYWORDS = [
    ("Kinase inhibitor", ["kinase inhibitor", "tyrosine kinase", "kinase blocker"]),
    ("Checkpoint inhibitor", ["checkpoint inhibitor", "pd-1", "pd-l1", "ctla-4", "ctla4"]),
    ("DNA damaging agent", ["dna damag", "alkylating", "topoisomerase", "dna intercalat", "dna cross-link"]),
    ("Pathway inhibitor", ["pathway inhibitor", "mtor inhibitor", "hedgehog", "wnt inhibitor", "mapk"]),
    ("Antimetabolite", ["antimetabolite", "folate antagonist", "nucleoside analog"]),
    ("Hormone / receptor modulator", ["receptor agonist", "receptor antagonist", "hormone"]),
]
_UNKNOWN_MOA = "Unknown / unclassified"


def _classify_moa(mechanism_text: str | None) -> str:
    if not mechanism_text:
        return _UNKNOWN_MOA
    text = mechanism_text.lower()
    for label, keywords in _MOA_KEYWORDS:
        if any(kw in text for kw in keywords):
            return label
    return _UNKNOWN_MOA


async def load_drug_moa_map() -> Dict[str, str]:
    """drug name -> coarse MoA class, from the drugs table."""
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(Drug.name, Drug.mechanism_of_action))).all()
    return {name: _classify_moa(moa) for name, moa in rows}


async def load_graph_and_model(checkpoint_path: str):
    async with AsyncSessionLocal() as session:
        builder = KnowledgeGraphBuilder(session)
        nx_graph = await builder.build_from_database()

    if nx_graph.number_of_nodes() == 0:
        raise RuntimeError("Empty knowledge graph — run ETL pipelines first.")

    data, node_lists = nx_to_heterodata(nx_graph)
    if "Drug" not in data.node_types or data["Drug"].x.size(0) == 0:
        raise RuntimeError("No Drug nodes in graph — run ETL first.")

    model = NeuroDrugHGT(metadata=data.metadata(), hidden_channels=128, num_layers=2, num_heads=4)
    predictor = DrugRepurposingPredictor(model)
    predictor.load_checkpoint(checkpoint_path)

    return data, node_lists, predictor


@torch.no_grad()
def get_drug_embeddings(data, predictor: DrugRepurposingPredictor) -> np.ndarray:
    x_dict = {k: data[k].x.to(predictor.device) for k in data.node_types}
    edge_index_dict = {k: data[k].edge_index.to(predictor.device) for k in data.edge_types}
    emb_dict = predictor.model.encode(x_dict, edge_index_dict)
    return emb_dict["Drug"].cpu().numpy()


def drug_display_name(node_key: str) -> str:
    # node keys look like "Drug:<chembl_id or name>" — strip the type prefix
    return node_key.split(":", 1)[1] if ":" in node_key else node_key


def plot_tsne(coords: np.ndarray, labels: List[str], names: List[str], out_path: str, perplexity: int):
    unique_labels = sorted(set(labels))
    cmap = plt.get_cmap("tab10" if len(unique_labels) <= 10 else "tab20")
    color_for = {lab: cmap(i % cmap.N) for i, lab in enumerate(unique_labels)}

    fig, ax = plt.subplots(figsize=(10, 8))
    for lab in unique_labels:
        idx = [i for i, l in enumerate(labels) if l == lab]
        ax.scatter(
            coords[idx, 0], coords[idx, 1],
            label=f"{lab} (n={len(idx)})",
            color=color_for[lab],
            s=45, alpha=0.8, edgecolors="white", linewidths=0.4,
        )

    ax.set_title(f"NeuroDrug HGT — Drug Embedding t-SNE (perplexity={perplexity})", fontsize=13)
    ax.set_xlabel("t-SNE dimension 1")
    ax.set_ylabel("t-SNE dimension 2")
    ax.legend(loc="best", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    logger.info(f"Saved t-SNE plot to {out_path}")


async def main(checkpoint_path: str, out_path: str, perplexity: int, n_iter: int):
    data, node_lists, predictor = await load_graph_and_model(checkpoint_path)
    embeddings = get_drug_embeddings(data, predictor)
    n_drugs = embeddings.shape[0]

    effective_perplexity = min(perplexity, max(2, n_drugs - 1))
    if effective_perplexity != perplexity:
        logger.warning(
            f"Requested perplexity={perplexity} exceeds n_drugs-1 ({n_drugs - 1}); "
            f"using {effective_perplexity} instead. Add more drugs via ETL for a more "
            f"stable projection."
        )

    tsne = TSNE(
        n_components=2,
        perplexity=effective_perplexity,
        n_iter=n_iter,
        init="pca",
        random_state=42,
    )
    coords = tsne.fit_transform(embeddings)

    moa_map = await load_drug_moa_map()
    drug_keys = node_lists["Drug"]
    names = [drug_display_name(k) for k in drug_keys]
    labels = [moa_map.get(name, _UNKNOWN_MOA) for name in names]

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    plot_tsne(coords, labels, names, out_path, effective_perplexity)

    coords_path = os.path.splitext(out_path)[0] + "_coords.json"
    with open(coords_path, "w") as f:
        json.dump(
            [
                {"drug": name, "x": float(x), "y": float(y), "moa_class": label}
                for name, (x, y), label in zip(names, coords, labels)
            ],
            f,
            indent=2,
        )
    logger.info(f"Saved coordinates to {coords_path}")

    label_counts: Dict[str, int] = {}
    for lab in labels:
        label_counts[lab] = label_counts.get(lab, 0) + 1
    print("\nMoA class distribution among embedded drugs:")
    for lab, count in sorted(label_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {lab:<32}{count}")
    if label_counts.get(_UNKNOWN_MOA, 0) / max(n_drugs, 1) > 0.5:
        print(
            "\nNote: most drugs fall in 'Unknown / unclassified' — this usually means "
            "Drug.mechanism_of_action is sparsely populated by the ChEMBL ETL step. "
            "Re-run ChEMBL ingestion with a query that includes the mechanism field, "
            "or extend _MOA_KEYWORDS in this script to match the text you do have."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a t-SNE plot of NeuroDrug's learned drug embeddings.")
    parser.add_argument("--checkpoint", default="checkpoints/best_model.pt")
    parser.add_argument("--out", default="checkpoints/drug_tsne.png")
    parser.add_argument("--perplexity", type=int, default=30, help="Proposal default: 30")
    parser.add_argument("--n-iter", type=int, default=1000, help="Proposal default: 1000")
    args = parser.parse_args()
    asyncio.run(main(args.checkpoint, args.out, args.perplexity, args.n_iter))
