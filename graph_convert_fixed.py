"""
Shared NetworkX → PyG HeteroData converter.
Used by both run_training.py and repurposing.py so inference metadata
is byte-for-byte identical to training — ensuring checkpoint weights load
without shape mismatches.

CRITICAL: FEATURE_DIM and all _*_feats functions must stay in sync with
backend/scripts/run_training.py. Divergence causes lin_dict weight shapes
to differ between training ([128,16]) and inference, which either silently
uses random projections (lazy Linear skip) or crashes on shape mismatch.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

import torch
from torch_geometric.data import HeteroData


# ── Feature dimension — must match run_training.py's FEATURE_DIM ─────────────
FEATURE_DIM = 16

_MONDO_TO_IDX: Dict[str, int] = {
    "MONDO_0018177": 0,   # Glioblastoma Multiforme
    "MONDO_0005072": 1,   # Neuroblastoma
    "MONDO_0012817": 2,   # Ewing Sarcoma
    "MONDO_0007959": 3,   # Medulloblastoma
    "MONDO_0019004": 4,   # Wilms Tumor
}
_NAME_TO_IDX: Dict[str, int] = {
    "glioblastoma": 0,
    "neuroblastoma": 1,
    "ewing": 2,
    "medulloblastoma": 3,
    "wilms": 4,
}


def _pad(feats: List[float]) -> List[float]:
    """Pad or truncate to FEATURE_DIM. Matches run_training.py's _pad()."""
    if len(feats) >= FEATURE_DIM:
        return feats[:FEATURE_DIM]
    return feats + [0.0] * (FEATURE_DIM - len(feats))


def _gene_feats(attrs: dict) -> List[float]:
    """Matches run_training.py's _gene_feats() exactly."""
    f = attrs.get("features") or {}
    return _pad([
        float(f.get("is_oncogene") or 0),
        float(f.get("is_tumor_suppressor") or 0),
    ])


def _drug_feats(attrs: dict) -> List[float]:
    """Matches run_training.py's _drug_feats() exactly."""
    f = attrs.get("features") or {}
    try:
        max_phase = float(f.get("max_phase") or 0) / 4.0
    except (TypeError, ValueError):
        max_phase = 0.0
    return _pad([max_phase])


def _disease_feats(attrs: dict) -> List[float]:
    """
    Matches run_training.py's _disease_feats() exactly.
    5-dim one-hot identifying which of the 5 target diseases this node
    represents, padded to FEATURE_DIM=16.

    Lookup strategy (same order as training):
      1. Scan all attr values (including injected '_node_key') for MONDO IDs
      2. Name-based keyword match
      3. All-zeros fallback
    """
    one_hot = [0.0] * len(_MONDO_TO_IDX)
    searchable = " ".join(str(v) for v in attrs.values() if v is not None)
    for mondo_id, idx in _MONDO_TO_IDX.items():
        if mondo_id in searchable:
            one_hot[idx] = 1.0
            return _pad(one_hot)
    name = (attrs.get("name") or "").lower()
    for keyword, idx in _NAME_TO_IDX.items():
        if keyword in name:
            one_hot[idx] = 1.0
            return _pad(one_hot)
    return _pad(one_hot)


FEAT_FN: Dict[str, callable] = {
    "Gene":    _gene_feats,
    "Drug":    _drug_feats,
    "Disease": _disease_feats,
}


def nx_to_heterodata(
    nx_graph,
) -> Tuple[HeteroData, Dict[str, List[str]]]:
    """
    Convert a NetworkX knowledge graph to a PyG HeteroData object.

    Reverse edges are added automatically so that Drug and Disease appear as
    message *destinations* in at least one edge type — HGTConv only outputs
    updated embeddings for destination node types.

    FIX: '_node_key' is injected into every attrs dict so _disease_feats()
    can extract MONDO IDs from the node key string (e.g. "Disease:MONDO_0018177")
    without a DB round-trip. Matches run_training.py's FIX-T2.

    Returns
    -------
    data       : PyG HeteroData ready for NeuroDrugHGT
    node_lists : {node_type: [node_key, ...]} ordered by local index
    """
    # ── 1. Group nodes by type ────────────────────────────────────────────
    node_lists: Dict[str, List[str]] = defaultdict(list)
    node_to_idx: Dict[str, Tuple[str, int]] = {}

    for node_key, attrs in nx_graph.nodes(data=True):
        ntype = attrs.get("node_type", "Unknown")
        idx = len(node_lists[ntype])
        node_lists[ntype].append(node_key)
        node_to_idx[node_key] = (ntype, idx)

    # ── 2. Build feature matrices ─────────────────────────────────────────
    data = HeteroData()
    for ntype, keys in node_lists.items():
        fn = FEAT_FN.get(ntype, lambda a: _pad([0.0]))
        # Inject '_node_key' so feature functions can use it for ID lookup
        feat_matrix = [fn({**nx_graph.nodes[k], "_node_key": str(k)}) for k in keys]
        data[ntype].x = torch.tensor(feat_matrix, dtype=torch.float)
        data[ntype].node_keys = keys

    # ── 3. Forward edges ──────────────────────────────────────────────────
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

    # ── 4. Reverse edges ─────────────────────────────────────────────────
    # Ensures Drug and Disease are also destinations so HGTConv produces
    # updated embeddings for them (not just the carry-forward fallback).
    for (src_type, rel, dst_type) in list(fwd_groups.keys()):
        rev_rel    = f"rev_{rel}"
        rev_triple = (dst_type, rev_rel, src_type)
        if rev_triple not in fwd_groups:
            rev_edges = [(d, s) for s, d in fwd_groups[(src_type, rel, dst_type)]]
            if rev_edges:
                ei = torch.tensor(rev_edges, dtype=torch.long).t().contiguous()
                data[dst_type, rev_rel, src_type].edge_index = ei

    return data, dict(node_lists)
