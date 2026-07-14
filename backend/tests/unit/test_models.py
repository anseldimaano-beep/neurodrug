import pytest
import numpy as np
from app.ml.metrics import compute_roc_auc, compute_average_precision, evaluate_all
from app.ml.features import build_gene_features, build_drug_features, build_disease_features
from app.ml.cross_validation import CrossValidator, BootstrapValidator, compute_all_metrics
from sklearn.linear_model import LogisticRegression


class TestMetrics:
    def test_roc_auc_perfect(self):
        y_true = np.array([1, 0, 1, 0])
        y_score = np.array([0.9, 0.1, 0.8, 0.2])
        assert compute_roc_auc(y_true, y_score) == 1.0

    def test_roc_auc_random(self):
        np.random.seed(42)
        y_true = np.random.randint(0, 2, 100)
        y_score = np.random.rand(100)
        auc = compute_roc_auc(y_true, y_score)
        assert 0.0 <= auc <= 1.0

    def test_average_precision(self):
        y_true = np.array([1, 0, 1, 0, 1])
        y_score = np.array([0.9, 0.1, 0.8, 0.2, 0.7])
        ap = compute_average_precision(y_true, y_score)
        assert ap > 0.9

    def test_evaluate_all_returns_all_keys(self):
        y_true = np.array([1, 0, 1, 0, 1, 0])
        y_score = np.array([0.9, 0.1, 0.8, 0.2, 0.7, 0.3])
        metrics = evaluate_all(y_true, y_score)
        assert "roc_auc" in metrics
        assert "average_precision" in metrics
        assert "hits@10" in metrics
        assert "mrr" in metrics


class TestFeatures:
    def test_gene_feature_shape(self):
        feat = build_gene_features(0.5, 10, 5, 3, 0.7, True, False)
        assert feat.shape == (7,)
        assert feat.dtype == np.float32

    def test_drug_feature_shape(self):
        feat = build_drug_features(True, 3, 450.0)
        assert feat.shape == (3,)

    def test_disease_feature_shape(self):
        feat = build_disease_features(50, 0.6)
        assert feat.shape == (2,)


class TestCrossValidation:
    def test_cross_validator_runs(self):
        np.random.seed(42)
        X = np.random.randn(200, 10)
        y = np.random.randint(0, 2, 200)
        cv = CrossValidator(n_splits=3, random_state=42)
        result = cv.validate(X, y, lambda: LogisticRegression(max_iter=100))
        assert "mean" in result
        assert "std" in result
        assert "fold_metrics" in result
        assert len(result["fold_metrics"]) == 3
        assert 0.0 <= result["mean"]["auroc"] <= 1.0

    def test_bootstrap_validator(self):
        np.random.seed(42)
        y_true = np.random.randint(0, 2, 100)
        y_score = np.random.rand(100)
        bv = BootstrapValidator(n_iterations=100)
        result = bv.validate(y_true, y_score)
        assert "auroc_ci_lower" in result
        assert "auroc_ci_upper" in result
        assert result["auroc_ci_lower"] <= result["auroc_ci_upper"]
