"""
Explainable AI (XAI) module: SHAP, Integrated Gradients, Attention Visualization.
"""
import numpy as np
import torch
from typing import Dict, List, Any, Optional, Tuple
from app.core.logging import logger


class SHAPExplainer:
    """SHAP values for any sklearn-compatible model."""

    def __init__(self, model, feature_names: List[str] = None):
        self.model = model
        self.feature_names = feature_names

    def explain(self, X: np.ndarray, background: np.ndarray = None, n_samples: int = 100) -> Dict[str, Any]:
        try:
            import shap
            if background is None:
                background = shap.sample(X, min(n_samples, len(X)))
            explainer = shap.KernelExplainer(
                self.model.predict_proba if hasattr(self.model, "predict_proba") else self.model.predict,
                background,
            )
            shap_values = explainer.shap_values(X[:min(50, len(X))], silent=True)
            if isinstance(shap_values, list):
                shap_values = shap_values[1]
            mean_abs = np.mean(np.abs(shap_values), axis=0)
            importance = {
                self.feature_names[i] if self.feature_names else f"feature_{i}": float(mean_abs[i])
                for i in range(len(mean_abs))
            }
            sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)
            return {
                "method": "shap",
                "shap_values": shap_values.tolist(),
                "feature_importance": dict(sorted_imp),
                "top_features": [{"name": k, "importance": v} for k, v in sorted_imp[:10]],
            }
        except ImportError:
            logger.warning("SHAP not installed. Install with: pip install shap")
            return {"method": "shap", "error": "shap not installed"}
        except Exception as e:
            logger.error(f"SHAP explainer failed: {e}")
            return {"method": "shap", "error": str(e)}


class IntegratedGradientsExplainer:
    """Integrated Gradients for PyTorch neural networks."""

    def __init__(self, model: torch.nn.Module, device: str = "cpu"):
        self.model = model.to(device)
        self.device = device

    def explain(
        self,
        input_tensor: torch.Tensor,
        baseline: Optional[torch.Tensor] = None,
        n_steps: int = 50,
    ) -> Dict[str, Any]:
        if baseline is None:
            baseline = torch.zeros_like(input_tensor)
        alphas = torch.linspace(0, 1, n_steps).to(self.device)
        gradients = []
        for alpha in alphas:
            interpolated = (baseline + alpha * (input_tensor - baseline)).requires_grad_(True)
            output = self.model(interpolated)
            if isinstance(output, dict):
                output = list(output.values())[0]
            output = output.mean()
            output.backward()
            gradients.append(interpolated.grad.detach().cpu().numpy())

        avg_grads = np.mean(gradients, axis=0)
        diff = (input_tensor - baseline).detach().cpu().numpy()
        integrated_grads = avg_grads * diff
        return {
            "method": "integrated_gradients",
            "integrated_gradients": integrated_grads.tolist(),
            "attribution_sum": float(integrated_grads.sum()),
            "n_steps": n_steps,
        }


class AttentionVisualizer:
    """Extract and visualize attention weights from HGT model."""

    def __init__(self, model: torch.nn.Module):
        self.model = model
        self._attention_cache: Dict[str, Any] = {}
        self._hooks = []

    def register_hooks(self):
        """Register forward hooks to capture attention weights."""
        for name, module in self.model.named_modules():
            if hasattr(module, "att_src") or "HGTConv" in type(module).__name__:
                hook = module.register_forward_hook(self._make_hook(name))
                self._hooks.append(hook)

    def _make_hook(self, name: str):
        def hook(module, input, output):
            if hasattr(module, "_alpha"):
                self._attention_cache[name] = module._alpha.detach().cpu()
        return hook

    def remove_hooks(self):
        for h in self._hooks:
            h.remove()
        self._hooks.clear()

    def get_attention_weights(self) -> Dict[str, np.ndarray]:
        return {k: v.numpy() for k, v in self._attention_cache.items()}


class GraphExplainer:
    """Graph-based explanations: important paths and subgraphs."""

    @staticmethod
    def find_explanation_paths(
        graph,
        drug_node: str,
        disease_node: str,
        max_paths: int = 5,
        max_path_length: int = 4,
    ) -> List[Dict[str, Any]]:
        """Find top explanation paths between drug and disease in NetworkX graph."""
        import networkx as nx
        try:
            all_paths = list(nx.all_simple_paths(
                graph.to_undirected(),
                source=drug_node,
                target=disease_node,
                cutoff=max_path_length,
            ))
            scored_paths = []
            for path in all_paths[:100]:
                edges = [(path[i], path[i+1]) for i in range(len(path)-1)]
                path_score = 1.0
                for u, v in edges:
                    edge_data = graph.get_edge_data(u, v)
                    if edge_data:
                        edge_attrs = list(edge_data.values())[0] if isinstance(edge_data, dict) else {}
                        path_score *= edge_attrs.get("weight", 1.0)
                scored_paths.append({
                    "path": path,
                    "length": len(path) - 1,
                    "score": float(path_score),
                    "node_types": [graph.nodes[n].get("node_type", "unknown") for n in path],
                })
            scored_paths.sort(key=lambda x: x["score"], reverse=True)
            return scored_paths[:max_paths]
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    @staticmethod
    def compute_node_importance(
        graph,
        target_node: str,
        drug_score: float,
    ) -> Dict[str, float]:
        """Compute importance of each neighboring node."""
        import networkx as nx
        importance = {}
        neighbors = list(graph.neighbors(target_node)) + list(graph.predecessors(target_node))
        for nb in neighbors:
            edge_data = graph.get_edge_data(target_node, nb) or graph.get_edge_data(nb, target_node)
            if edge_data:
                attrs = list(edge_data.values())[0] if isinstance(edge_data, dict) else {}
                importance[nb] = float(attrs.get("weight", 1.0) * drug_score)
        return dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))
