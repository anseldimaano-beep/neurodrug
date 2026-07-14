"""
Benchmarking framework comparing traditional ML vs graph models.
"""
import numpy as np
import time
from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass, field, asdict
from app.ml.metrics import compute_roc_auc, compute_average_precision, compute_hits_at_k, compute_mrr, compute_ndcg
from app.ml.cross_validation import CrossValidator, compute_all_metrics
from app.core.logging import logger


@dataclass
class BenchmarkResult:
    model_name: str
    model_type: str  # "traditional" | "graph"
    metrics: Dict[str, float] = field(default_factory=dict)
    cv_mean: Dict[str, float] = field(default_factory=dict)
    cv_std: Dict[str, float] = field(default_factory=dict)
    train_time_seconds: float = 0.0
    inference_time_seconds: float = 0.0
    n_parameters: Optional[int] = None
    hyperparameters: Dict[str, Any] = field(default_factory=dict)


class BenchmarkRunner:
    """Compare multiple models on the same dataset."""

    def __init__(self, n_splits: int = 5, random_state: int = 42):
        self.n_splits = n_splits
        self.random_state = random_state
        self.results: List[BenchmarkResult] = []

    def run_sklearn_model(
        self,
        name: str,
        model_factory: Callable,
        model_type: str,
        X: np.ndarray,
        y: np.ndarray,
        hyperparameters: Dict = None,
    ) -> BenchmarkResult:
        logger.info(f"Benchmarking {name}...")
        cv = CrossValidator(n_splits=self.n_splits, random_state=self.random_state)

        t0 = time.perf_counter()
        cv_result = cv.validate(X, y, model_factory)
        train_time = time.perf_counter() - t0

        # Full dataset eval
        model = model_factory()
        model.fit(X, y)
        t_inf = time.perf_counter()
        y_score = model.predict_proba(X)[:, 1]
        inf_time = time.perf_counter() - t_inf

        full_metrics = compute_all_metrics(y, y_score)

        result = BenchmarkResult(
            model_name=name,
            model_type=model_type,
            metrics=full_metrics,
            cv_mean=cv_result["mean"],
            cv_std=cv_result["std"],
            train_time_seconds=train_time,
            inference_time_seconds=inf_time,
            hyperparameters=hyperparameters or {},
        )
        self.results.append(result)
        logger.info(f"  {name}: cv_auroc={cv_result['mean']['auroc']:.4f} ± {cv_result['std']['auroc']:.4f}")
        return result

    def add_graph_result(self, result: BenchmarkResult):
        self.results.append(result)

    def generate_leaderboard(self) -> List[Dict[str, Any]]:
        """Generate sorted leaderboard by CV AUROC."""
        board = []
        for r in self.results:
            board.append({
                "rank": 0,
                "model": r.model_name,
                "type": r.model_type,
                "cv_auroc": r.cv_mean.get("auroc", 0.0),
                "cv_auprc": r.cv_mean.get("auprc", 0.0),
                "cv_f1": r.cv_mean.get("f1", 0.0),
                "cv_auroc_std": r.cv_std.get("auroc", 0.0),
                "train_time_s": r.train_time_seconds,
                "hyperparameters": r.hyperparameters,
            })
        board.sort(key=lambda x: x["cv_auroc"], reverse=True)
        for i, row in enumerate(board):
            row["rank"] = i + 1
        return board

    def summary(self) -> str:
        board = self.generate_leaderboard()
        lines = ["=" * 70, "BENCHMARK LEADERBOARD", "=" * 70]
        header = f"{'Rank':4} {'Model':30} {'Type':12} {'AUROC':8} {'AUPRC':8} {'F1':8}"
        lines.append(header)
        lines.append("-" * 70)
        for row in board:
            lines.append(
                f"{row['rank']:4} {row['model']:30} {row['type']:12} "
                f"{row['cv_auroc']:.4f}   {row['cv_auprc']:.4f}   {row['cv_f1']:.4f}"
            )
        lines.append("=" * 70)
        return "\n".join(lines)
