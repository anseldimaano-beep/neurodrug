"""
edge_filter.py — restrict a PyG HeteroData edge_index_dict to a subset of
biological edge categories for ablation studies.

Proposal reference (Section D, Step 3.2 — Ablation Study):
    "Four additional HGT models are trained with progressively reduced
    edge type sets: PPI-only, Drug-Target-only, Gene-Disease-only, and
    PPI + Drug-Target (omitting gene-disease)."

Edge categories in the live knowledge graph (see services/etl/orchestrator.py):
    PPI          — Gene <-> Gene   (STRING)
    DrugTarget   — Drug <-> Gene   (DGIdb)
    GeneDisease  — Gene <-> Disease (Open Targets)
    ClinicalTrial (and any other Drug<->Disease relation) is the
        drug-repurposing LINK PREDICTION TARGET itself, not an input
        feature edge — it is always left in place so every ablation
        variant is still solving the same task. Only the PPI / DrugTarget
        / GeneDisease *support* edges are toggled.

    NOTE: the proposal's original design also specifies a "co-mutation"
    (Gene-Gene, derived from TCGA co-occurrence) edge type. That edge type
    is not yet populated by the current ETL pipeline (services/etl/gdc.py
    ingests somatic mutation records but does not yet derive co-mutation
    Gene-Gene edges), so it is omitted here. Add a "CoMutation" category
    below once that ETL step exists.
"""
from __future__ import annotations

from typing import Dict, Iterable, Tuple

import torch

# Relation-name -> category. Reverse edges are named f"rev_{relation}" by
# graph_convert.nx_to_heterodata, so we strip that prefix before matching.
_CATEGORY_BY_RELATION = {
    "PPI": "PPI",
    "DrugTarget": "DrugTarget",
    "GeneDisease": "GeneDisease",
    # "CoMutation": "CoMutation",  # not yet ETL'd — see module docstring
}

# Node-type pairs that represent the Drug-Disease prediction target itself.
# These edge types are always kept regardless of which categories are
# ablated, since removing them would remove the label, not a feature.
_ALWAYS_KEEP_NODE_PAIRS = {("Drug", "Disease"), ("Disease", "Drug")}


def edge_category(relation: str) -> str | None:
    """Map a (possibly reversed) relation name to its ablation category."""
    rel = relation[4:] if relation.startswith("rev_") else relation
    return _CATEGORY_BY_RELATION.get(rel)


def filter_edge_index_dict(
    edge_index_dict: Dict[Tuple[str, str, str], torch.Tensor],
    keep_categories: Iterable[str],
) -> Dict[Tuple[str, str, str], torch.Tensor]:
    """
    Return a new edge_index_dict containing only:
      - edges whose category is in `keep_categories`, and
      - Drug<->Disease edges (the prediction target — always kept).

    `keep_categories` should be a subset of {"PPI", "DrugTarget", "GeneDisease"}.
    Pass an empty set to keep only the Drug<->Disease target edges (a
    structure-free / trivial baseline, useful as a sanity floor).
    """
    keep = set(keep_categories)
    out: Dict[Tuple[str, str, str], torch.Tensor] = {}

    for triple, ei in edge_index_dict.items():
        src_type, relation, dst_type = triple
        if (src_type, dst_type) in _ALWAYS_KEEP_NODE_PAIRS:
            out[triple] = ei
            continue
        cat = edge_category(relation)
        if cat is not None and cat in keep:
            out[triple] = ei

    return out


def mask_target_edges(
    edge_index_dict: Dict[Tuple[str, str, str], torch.Tensor],
    exclude_pairs,
    src_type: str = "Drug",
    dst_type: str = "Disease",
) -> Dict[Tuple[str, str, str], torch.Tensor]:
    """
    Remove specific (src_idx, dst_idx) pairs from every Drug<->Disease edge
    type in `edge_index_dict` — both the forward (Drug, rel, Disease) and
    reverse (Disease, rev_rel, Drug) directions.

    Why this exists: nx_to_heterodata puts EVERY Drug-Disease edge (train,
    val, and any future test split) into the graph used for message passing.
    HGTConv (and every other GNN baseline) then aggregates over those edges
    when computing a Disease node's embedding — including the exact edges
    being predicted. That's transductive label leakage: a Disease node can
    "see" whether it's connected to a given Drug before the model is asked
    to predict that connection. It doesn't just inflate absolute AUC, it can
    invert relative comparisons (e.g. an edge-sparse ablation variant looks
    *better* than the full model, because the target edges make up a larger
    share of what each node attends to when there's less other structure to
    dilute them).

    Call this with `exclude_pairs = val_pos` (and `+ test_pos`, once a test
    split exists) BEFORE building any Batch/edge_index_dict used for
    training or evaluation — for both the train and val loaders, so the
    model only ever sees the training-edge subgraph. This mirrors the
    standard PyG `RandomLinkSplit` transductive setup.
    """
    exclude = set((int(s), int(d)) for s, d in exclude_pairs)
    out: Dict[Tuple[str, str, str], torch.Tensor] = {}

    for (t_src, rel, t_dst), ei in edge_index_dict.items():
        if ei.numel() == 0 or not exclude:
            out[(t_src, rel, t_dst)] = ei
            continue

        if t_src == src_type and t_dst == dst_type:
            pairs = list(zip(ei[0].tolist(), ei[1].tolist()))
            keep = [p not in exclude for p in pairs]
        elif t_src == dst_type and t_dst == src_type:
            pairs = list(zip(ei[1].tolist(), ei[0].tolist()))  # (drug, disease) even though edge is disease->drug
            keep = [p not in exclude for p in pairs]
        else:
            out[(t_src, rel, t_dst)] = ei
            continue

        keep_idx = torch.tensor([i for i, k in enumerate(keep) if k], dtype=torch.long)
        out[(t_src, rel, t_dst)] = ei[:, keep_idx] if keep_idx.numel() > 0 else ei[:, :0]

    return out


def override_edge_index_dict(dataset, edge_index_dict: Dict[Tuple[str, str, str], torch.Tensor]) -> None:
    """
    Monkey-patch a DrugDiseaseDataset (or any dataset whose __getitem__
    returns a Batch with an `edge_index_dict` attribute) so every batch it
    yields uses this fixed, pre-masked edge_index_dict for message passing —
    instead of rebuilding an unmasked one from the dataset's underlying
    HeteroData on every __getitem__ call.
    """
    original_getitem = dataset.__class__.__getitem__

    def patched(self, idx):
        batch = original_getitem(self, idx)
        batch.edge_index_dict = edge_index_dict
        return batch

    dataset.__getitem__ = patched.__get__(dataset, dataset.__class__)


# Named variants matching the proposal's Step 3.2 ablation plan.
ABLATION_VARIANTS: Dict[str, set] = {
    "full_model":            {"PPI", "DrugTarget", "GeneDisease"},
    "ppi_only":               {"PPI"},
    "drug_target_only":       {"DrugTarget"},
    "gene_disease_only":      {"GeneDisease"},
    "ppi_plus_drug_target":   {"PPI", "DrugTarget"},
}
