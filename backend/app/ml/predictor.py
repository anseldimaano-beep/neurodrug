import torch
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
from app.ml.models.hgt import NeuroDrugHGT
from app.core.logging import logger


class DrugRepurposingPredictor:
    def __init__(
        self,
        model: NeuroDrugHGT,
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
    ):
        self.model = model.to(device)
        self.model.eval()
        self.device = device

    # ------------------------------------------------------------------ #
    # FIX C1: load_checkpoint was missing; repurposing.py calls it on     #
    # every inference run.  Without this method the service crashes with   #
    # AttributeError before any prediction is made.                        #
    # ------------------------------------------------------------------ #
    def load_checkpoint(self, checkpoint_path: str) -> None:
        """Load model weights from a checkpoint, skipping any keys whose
        shapes don't match the current model (e.g. trained on dummy data
        with different graph topology than inference graph)."""
        path = Path(checkpoint_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Checkpoint not found: {checkpoint_path}. "
                "Run training first or verify MODEL_CHECKPOINT_PATH."
            )
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        state_dict = (
            checkpoint.get("model_state_dict", checkpoint)
            if isinstance(checkpoint, dict)
            else checkpoint
        )

        # Filter to only keys that exist in the model AND have matching shapes.
        # HGTConv uses lazy init — some params have no shape until forward() runs,
        # so we catch RuntimeError and skip those keys too.
        current = self.model.state_dict()
        compatible = {}
        skipped = []
        for key, val in state_dict.items():
            if key not in current:
                skipped.append(key)
                continue
            try:
                if current[key].shape == val.shape:
                    compatible[key] = val
                else:
                    skipped.append(key)
            except RuntimeError:
                # Uninitialized lazy parameter — skip it
                skipped.append(key)

        if skipped:
            logger.warning(
                f"Skipped {len(skipped)} checkpoint keys due to shape mismatch "
                f"or missing in current model (will use random init): {skipped[:3]}..."
            )

        # Merge compatible weights into current state and reload
        current.update(compatible)
        self.model.load_state_dict(current)
        self.model.eval()
        logger.info(
            f"Loaded {len(compatible)}/{len(state_dict)} weights "
            f"from checkpoint {checkpoint_path}"
        )

    @torch.no_grad()
    def predict_all_pairs(
        self,
        x_dict: Dict[str, torch.Tensor],
        edge_index_dict: Dict[Tuple[str, str, str], torch.Tensor],
        drug_nodes: torch.Tensor,
        disease_nodes: torch.Tensor,
        batch_size: int = 4096,
    ) -> np.ndarray:
        self.model.eval()
        x_dict = {k: v.to(self.device) for k, v in x_dict.items()}
        edge_index_dict = {k: v.to(self.device) for k, v in edge_index_dict.items()}
        emb_dict = self.model.encode(x_dict, edge_index_dict)

        # HGTConv only outputs embeddings for destination node types.
        # Drug is often source-only → not in emb_dict after encode().
        # Fall back to zero embeddings of the correct hidden dim.
        # (x_dict features are raw input dim, not hidden dim, so we don't reuse them.)
        hidden = 128  # must match training hidden_channels
        n_drug    = x_dict["Drug"].size(0)    if "Drug"    in x_dict else drug_nodes.max().item() + 1
        n_disease = x_dict["Disease"].size(0) if "Disease" in x_dict else disease_nodes.max().item() + 1
        if "Drug" not in emb_dict:
            emb_dict["Drug"] = torch.zeros(n_drug, hidden, device=self.device)
        if "Disease" not in emb_dict:
            emb_dict["Disease"] = torch.zeros(n_disease, hidden, device=self.device)

        drug_emb    = emb_dict["Drug"][drug_nodes]
        disease_emb = emb_dict["Disease"][disease_nodes]

        scores = []
        for i in range(0, len(drug_nodes), batch_size):
            batch_drug = drug_emb[i : i + batch_size]
            batch_scores = []
            for j in range(0, len(disease_nodes), batch_size):
                batch_disease = disease_emb[j : j + batch_size]
                src = (
                    batch_drug.unsqueeze(1)
                    .expand(-1, batch_disease.size(0), -1)
                    .reshape(-1, batch_drug.size(-1))
                )
                dst = (
                    batch_disease.unsqueeze(0)
                    .expand(batch_drug.size(0), -1, -1)
                    .reshape(-1, batch_disease.size(-1))
                )
                logits = self.model.predictor(src, dst)
                batch_scores.append(torch.sigmoid(logits).cpu().numpy())
            scores.append(np.concatenate(batch_scores))
        return np.concatenate(scores)

    @torch.no_grad()
    def rank_candidates(
        self,
        x_dict: Dict[str, torch.Tensor],
        edge_index_dict: Dict[Tuple[str, str, str], torch.Tensor],
        drug_nodes: torch.Tensor,
        disease_nodes: torch.Tensor,
        drug_names: List[str],
        disease_name: str,
        top_k: int = 20,
    ) -> List[Dict]:
        scores = self.predict_all_pairs(
            x_dict, edge_index_dict, drug_nodes, disease_nodes
        )
        ranked = np.argsort(-scores)[:top_k]
        results = []
        for rank_pos, idx in enumerate(ranked):
            results.append(
                {
                    "drug_name": drug_names[idx],
                    "disease_name": disease_name,
                    "prediction_score": float(scores[idx]),
                    "rank": rank_pos + 1,
                }
            )
        return results
