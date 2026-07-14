"""
Comprehensive cross-validation framework for drug repurposing models.
Supports k-fold, nested CV, bootstrap, and temporal validation.
"""
import numpy as np
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    f1_score, precision_score, recall_score,
    matthews_corrcoef, brier_score_loss,
)
from typing import Dict, List, Any, Callable, Optional
from app.core.logging import logger


def compute_all_metrics(y_true: np.ndarray, y_score: np.ndarray, threshold: float = 0.5) -> Dict[str, float]:
    y_pred = (y_score >= threshold).astype(int)
    return {
        "auroc":     float(roc_auc_score(y_true, y_score)),
        "auprc":     float(average_precision_score(y_true, y_score)),
        "f1":        float(f1_score(y_true, y_pred, zero_division=0)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall":    float(recall_score(y_true, y_pred, zero_division=0)),
        "mcc":       float(matthews_corrcoef(y_true, y_pred)),
        "brier":     float(brier_score_loss(y_true, y_score)),
        "n_positive": int(y_true.sum()),
        "n_total":   int(len(y_true)),
    }


class CrossValidator:
    def __init__(self, n_splits: int = 5, random_state: int = 42):
        self.n_splits = n_splits
        self.kf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)

    def validate(self, X: np.ndarray, y: np.ndarray, model_factory: Callable, **fit_kwargs) -> Dict[str, Any]:
        fold_metrics = []
        for fold, (train_idx, val_idx) in enumerate(self.kf.split(X, y)):
            model = model_factory()
            model.fit(X[train_idx], y[train_idx], **fit_kwargs)
            y_score = model.predict_proba(X[val_idx])[:, 1]
            m = compute_all_metrics(y[val_idx], y_score)
            m["fold"] = fold
            fold_metrics.append(m)
            logger.info(f"Fold {fold+1}/{self.n_splits} AUROC={m['auroc']:.4f}")
        keys = [k for k in fold_metrics[0] if k != "fold"]
        return {
            "fold_metrics": fold_metrics,
            "mean": {k: float(np.mean([m[k] for m in fold_metrics])) for k in keys},
            "std":  {k: float(np.std ([m[k] for m in fold_metrics])) for k in keys},
            "n_splits": self.n_splits,
        }


class NestedCrossValidator:
    def __init__(self, outer_splits: int = 5, inner_splits: int = 3, random_state: int = 42):
        self.outer = StratifiedKFold(n_splits=outer_splits, shuffle=True, random_state=random_state)
        self.inner = StratifiedKFold(n_splits=inner_splits, shuffle=True, random_state=random_state + 1)

    def validate(self, X: np.ndarray, y: np.ndarray, model_factory: Callable, param_grid: List[Dict]) -> Dict:
        outer_scores, best_params_list = [], []
        for o_fold, (tr, te) in enumerate(self.outer.split(X, y)):
            best_score, best_params = -1, param_grid[0]
            for params in param_grid:
                inner_aucs = []
                for _, (itr, ival) in enumerate(self.inner.split(X[tr], y[tr])):
                    m = model_factory(**params)
                    m.fit(X[tr[itr]], y[tr[itr]])
                    inner_aucs.append(roc_auc_score(y[tr[ival]], m.predict_proba(X[tr[ival]])[:, 1]))
                s = float(np.mean(inner_aucs))
                if s > best_score:
                    best_score, best_params = s, params
            final = model_factory(**best_params)
            final.fit(X[tr], y[tr])
            m = compute_all_metrics(y[te], final.predict_proba(X[te])[:, 1])
            m["outer_fold"] = o_fold
            m["best_params"] = best_params
            outer_scores.append(m)
            best_params_list.append(best_params)
        keys = [k for k in outer_scores[0] if k not in ("outer_fold", "best_params")]
        return {
            "fold_metrics": outer_scores,
            "mean": {k: float(np.mean([m[k] for m in outer_scores])) for k in keys},
            "std":  {k: float(np.std ([m[k] for m in outer_scores])) for k in keys},
            "best_params_per_fold": best_params_list,
        }


class BootstrapValidator:
    def __init__(self, n_iterations: int = 1000, random_state: int = 42):
        self.n_iterations = n_iterations
        self.rng = np.random.RandomState(random_state)

    def validate(self, y_true: np.ndarray, y_score: np.ndarray, ci_level: float = 0.95) -> Dict:
        boot_aucs = []
        for _ in range(self.n_iterations):
            idx = self.rng.choice(len(y_true), size=len(y_true), replace=True)
            if len(np.unique(y_true[idx])) < 2:
                continue
            boot_aucs.append(roc_auc_score(y_true[idx], y_score[idx]))
        alpha = 1 - ci_level
        base = compute_all_metrics(y_true, y_score)
        return {
            **base,
            "auroc_ci_lower": float(np.percentile(boot_aucs, 100 * alpha / 2)),
            "auroc_ci_upper": float(np.percentile(boot_aucs, 100 * (1 - alpha / 2))),
            "n_bootstrap": len(boot_aucs),
        }


class TemporalValidator:
    def __init__(self, n_splits: int = 4):
        self.n_splits = n_splits

    def validate(self, X: np.ndarray, y: np.ndarray, timestamps: np.ndarray, model_factory: Callable) -> Dict:
        idx = np.argsort(timestamps)
        X, y = X[idx], y[idx]
        sz = len(y) // (self.n_splits + 1)
        fold_metrics = []
        for s in range(1, self.n_splits + 1):
            tr_end = s * sz
            X_tr, y_tr = X[:tr_end], y[:tr_end]
            X_te, y_te = X[tr_end:tr_end + sz], y[tr_end:tr_end + sz]
            if len(np.unique(y_te)) < 2:
                continue
            m_obj = model_factory()
            m_obj.fit(X_tr, y_tr)
            m = compute_all_metrics(y_te, m_obj.predict_proba(X_te)[:, 1])
            m["split"] = s
            fold_metrics.append(m)
        keys = [k for k in fold_metrics[0] if k != "split"]
        return {
            "fold_metrics": fold_metrics,
            "mean": {k: float(np.mean([m[k] for m in fold_metrics])) for k in keys},
            "std":  {k: float(np.std ([m[k] for m in fold_metrics])) for k in keys},
        }
