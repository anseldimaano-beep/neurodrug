import numpy as np
from typing import Dict, List, Any


def build_gene_features(
    mutation_freq: float,
    ppi_degree: int,
    drug_target_count: int,
    disease_assoc_count: int,
    mean_ot_score: float,
    is_oncogene: bool,
    is_tumor_suppressor: bool,
) -> np.ndarray:
    return np.array([
        mutation_freq,
        float(ppi_degree),
        float(drug_target_count),
        float(disease_assoc_count),
        mean_ot_score,
        float(is_oncogene),
        float(is_tumor_suppressor),
    ], dtype=np.float32)


def build_drug_features(
    fda_approved: bool,
    num_targets: int,
    molecular_weight: float,
) -> np.ndarray:
    return np.array([
        float(fda_approved),
        float(num_targets),
        molecular_weight / 1000.0,
    ], dtype=np.float32)


def build_disease_features(
    associated_gene_count: int,
    mean_ot_score: float,
) -> np.ndarray:
    return np.array([
        float(associated_gene_count),
        mean_ot_score,
    ], dtype=np.float32)
