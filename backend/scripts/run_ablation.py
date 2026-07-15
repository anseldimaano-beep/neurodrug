"""
run_ablation.py — Edge-type ablation study (Proposal Section D, Step 3.2 /
Section F, "Ablation Study Analysis").

Trains the HGT link predictor five times on the real knowledge graph loaded
from PostgreSQL, each time restricted to a different subset of biological
edge categories, and reports the marginal AUC contribution of each edge
type:

    ΔAUC(edge type e) = AUC(full model, all edge types)
                       − AUC(model trained without edge type e)

Variants (see backend/app/ml/edge_filter.py for the exact definitions):
    full_model            — PPI + DrugTarget + GeneDisease   (baseline)
    ppi_only              — PPI
    drug_target_only      — DrugTarget
    gene_disease_only     — GeneDisease
    ppi_plus_drug_target  — PPI + DrugTarget   (GeneDisease omitted)

Usage (from the Docker container):
    docker-compose exec api python scripts/run_ablation.py
    docker-compose exec api python scripts/run_ablation.py --epochs 40 --patience 10

Results are written to checkpoints/ablation_results.json and printed as a
table. Each variant gets its own checkpoint subdirectory
(checkpoints/ablation/<variant_name>/) so full-model training elsewhere is
never overwritten.

NOTE ON TRANSDUCTIVE LEAKAGE: like run_training.py, this script does not
mask train/val Drug-Disease edges out of the message-passing graph itself
(only out of the positive/negative pair *labels*). That is an existing
property of the training pipeline, not something introduced by ablation —
each variant is affected identically, so relative ΔAUC comparisons remain
valid even though absolute AUC values are optimistic.
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# so we can reuse the exact same dataset / split / feature logic as the
# main training run — no drift between "how the full model was trained"
# and "how the ablation full_model baseline is trained".
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Dict, List

import torch
from torch.utils.data import DataLoader

from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.graph.builder import KnowledgeGraphBuilder
from app.ml.edge_filter import (
    ABLATION_VARIANTS,
    filter_edge_index_dict,
    mask_target_edges,
    override_edge_index_dict,
)
from app.ml.models.hgt import NeuroDrugHGT
from app.ml.trainer import HGTTrainer

from run_training import (  # noqa: E402  (same directory, see sys.path above)
    build_splits,
    DrugDiseaseDataset,
    nx_to_heterodata,
)


async def load_data():
    logger.info("Connecting to database ...")
    async with AsyncSessionLocal() as session:
        builder = KnowledgeGraphBuilder(session)
        nx_graph = await builder.build_from_database()

    n_nodes, n_edges = nx_graph.number_of_nodes(), nx_graph.number_of_edges()
    logger.info(f"Loaded graph: {n_nodes} nodes, {n_edges} edges")
    if n_nodes == 0:
        raise RuntimeError("Empty knowledge graph — run ETL pipelines first.")

    data, _ = nx_to_heterodata(nx_graph)
    n_drug = data["Drug"].x.size(0) if "Drug" in data.node_types else 0
    n_disease = data["Disease"].x.size(0) if "Disease" in data.node_types else 0
    if n_drug == 0 or n_disease == 0:
        raise RuntimeError("No Drug or Disease nodes in graph — run ETL first.")

    return data, n_drug, n_disease


def run_variant(
    variant_name: str,
    keep_categories: set,
    data,
    n_drug: int,
    n_disease: int,
    epochs: int,
    patience: int,
    batch_size: int = 4096,
) -> Dict:
    logger.info(f"\n{'=' * 60}\nAblation variant: {variant_name}  (edges kept: {sorted(keep_categories) or 'none'})\n{'=' * 60}")

    train_pos, val_pos, train_neg, val_neg = build_splits(data, n_drug, n_disease)

    # FIX-L1 (transductive leakage — see app/ml/edge_filter.py): mask val
    # positives out of the message-passing graph BEFORE restricting to this
    # variant's edge categories, so every variant is evaluated on equal
    # footing with no leakage, and ΔAUC reflects real information content
    # rather than how much of the label leaks through fewer categories.
    full_edge_index_dict = {k: data[k].edge_index for k in data.edge_types}
    leakage_safe_edge_index_dict = mask_target_edges(full_edge_index_dict, exclude_pairs=val_pos)
    variant_edge_index_dict = filter_edge_index_dict(leakage_safe_edge_index_dict, keep_categories)

    train_ds = DrugDiseaseDataset(data, train_pos, train_neg, batch_size=batch_size)
    val_ds = DrugDiseaseDataset(data, val_pos, val_neg, batch_size=batch_size)
    override_edge_index_dict(train_ds, variant_edge_index_dict)
    override_edge_index_dict(val_ds, variant_edge_index_dict)

    train_loader = DataLoader(train_ds, batch_size=1, collate_fn=lambda x: x[0])
    val_loader = DataLoader(val_ds, batch_size=1, collate_fn=lambda x: x[0])

    model = NeuroDrugHGT(
        metadata=data.metadata(),
        hidden_channels=128,
        num_layers=2,
        num_heads=4,
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    checkpoint_dir = os.path.join("checkpoints", "ablation", variant_name)
    trainer = HGTTrainer(
        model,
        device=device,
        lr=1e-3,
        max_epochs=epochs,
        patience=patience,
        metadata=data.metadata(),
    )
    trainer.checkpoint_dir = checkpoint_dir
    os.makedirs(checkpoint_dir, exist_ok=True)

    trainer.fit(train_loader, val_loader)

    final_metrics = trainer.history[-1] if trainer.history else {}
    return {
        "variant": variant_name,
        "edge_categories": sorted(keep_categories),
        "best_val_auc": trainer.best_val_auc,
        "final_metrics": final_metrics,
        "epochs_run": len(trainer.history),
    }


async def main(epochs: int, patience: int, batch_size: int):
    data, n_drug, n_disease = await load_data()

    results: List[Dict] = []
    for variant_name, keep_categories in ABLATION_VARIANTS.items():
        result = run_variant(variant_name, keep_categories, data, n_drug, n_disease, epochs, patience, batch_size)
        results.append(result)
        logger.info(f"{variant_name}: best_val_auc={result['best_val_auc']:.4f}")

    full_auc = next(r["best_val_auc"] for r in results if r["variant"] == "full_model")
    for r in results:
        r["delta_auc_vs_full"] = round(r["best_val_auc"] - full_auc, 4) if r["variant"] != "full_model" else 0.0

    os.makedirs("checkpoints", exist_ok=True)
    out_path = os.path.join("checkpoints", "ablation_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 72)
    print(f"{'Variant':<24}{'Edge types kept':<32}{'Val AUC':<10}{'Δ vs full':<10}")
    print("-" * 72)
    for r in results:
        print(f"{r['variant']:<24}{','.join(r['edge_categories']):<32}{r['best_val_auc']:<10.4f}{r['delta_auc_vs_full']:<+10.4f}")
    print("=" * 72)
    print(f"Full results written to {out_path}")
    print(
        "\nInterpretation: a large negative ΔAUC for the *_only variant means that "
        "removing the other edge types hurt performance a lot, i.e. that edge type "
        "was NOT sufficient on its own. A ΔAUC near 0 for ppi_plus_drug_target (vs. "
        "full_model) means Gene-Disease edges from Open Targets contribute little "
        "marginal signal once PPI + DrugTarget are present."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run edge-type ablation study for NeuroDrug's HGT model.")
    parser.add_argument("--epochs", type=int, default=60, help="Max epochs per variant (default: 60, vs. 100 for the full production run — kept lower since we train 5 models).")
    parser.add_argument("--patience", type=int, default=12, help="Early-stopping patience per variant.")
    parser.add_argument(
        "--batch-size", type=int, default=4096,
        help="Pairs per mini-batch (default: full-batch — see run_training.py's --batch-size help for why this matters for CPU speed).",
    )
    args = parser.parse_args()
    asyncio.run(main(args.epochs, args.patience, args.batch_size))
