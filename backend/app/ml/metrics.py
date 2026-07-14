import numpy as np
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve
from typing import Dict, List, Tuple


def compute_roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    return roc_auc_score(y_true, y_score)


def compute_average_precision(y_true: np.ndarray, y_score: np.ndarray) -> float:
    return average_precision_score(y_true, y_score)


def compute_hits_at_k(y_true: np.ndarray, y_score: np.ndarray, k: int = 10) -> float:
    order = np.argsort(-y_score)
    top_k = order[:k]
    hits = np.sum(y_true[top_k])
    return float(hits) / float(max(np.sum(y_true), 1))


def compute_mrr(y_true: np.ndarray, y_score: np.ndarray) -> float:
    order = np.argsort(-y_score)
    ranks = []
    for idx in np.where(y_true == 1)[0]:
        rank = np.where(order == idx)[0][0] + 1
        ranks.append(1.0 / rank)
    return np.mean(ranks) if ranks else 0.0


def compute_ndcg(y_true: np.ndarray, y_score: np.ndarray, k: int = 10) -> float:
    order = np.argsort(-y_score)[:k]
    dcg = np.sum((2 ** y_true[order] - 1) / np.log2(np.arange(2, k + 2)))
    ideal = np.sort(y_true)[::-1][:k]
    idcg = np.sum((2 ** ideal - 1) / np.log2(np.arange(2, k + 2)))
    return float(dcg / idcg) if idcg > 0 else 0.0


def evaluate_all(y_true: np.ndarray, y_score: np.ndarray) -> Dict[str, float]:
    return {
        "roc_auc": compute_roc_auc(y_true, y_score),
        "average_precision": compute_average_precision(y_true, y_score),
        "hits@10": compute_hits_at_k(y_true, y_score, k=10),
        "hits@20": compute_hits_at_k(y_true, y_score, k=20),
        "mrr": compute_mrr(y_true, y_score),
        "ndcg@10": compute_ndcg(y_true, y_score, k=10),
    }


def permutation_test(y_true: np.ndarray, y_score_hgt: np.ndarray, y_score_baseline: np.ndarray, n_permutations: int = 1000) -> float:
    observed_diff = compute_roc_auc(y_true, y_score_hgt) - compute_roc_auc(y_true, y_score_baseline)
    count = 0
    rng = np.random.RandomState(42)
    for _ in range(n_permutations):
        perm = rng.permutation(len(y_true))
        perm_y = y_true[perm]
        diff = compute_roc_auc(perm_y, y_score_hgt) - compute_roc_auc(perm_y, y_score_baseline)
        if diff >= observed_diff:
            count += 1
    return count / n_permutations
