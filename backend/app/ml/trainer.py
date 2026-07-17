import os
import json
import numpy as np
import torch
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from typing import Dict, Optional, List, Tuple
from app.ml.models.hgt import NeuroDrugHGT
from app.ml.metrics import evaluate_all
from app.core.logging import logger


class HGTTrainer:
    def __init__(
        self,
        model: NeuroDrugHGT,
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
        lr: float = 3e-4,
        weight_decay: float = 1e-5,
        max_epochs: int = 200,
        patience: int = 25,
        min_epochs: int = 0,
        grad_clip: float = 1.0,
        metadata: Optional[Tuple] = None,   # ← FIX: save graph topology with checkpoint
    ):
        self.model = model.to(device)
        self.device = device
        self.optimizer = AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
        self.scheduler = CosineAnnealingLR(self.optimizer, T_max=max_epochs, eta_min=1e-5)
        self.max_epochs = max_epochs
        self.patience = patience
        self.min_epochs = min_epochs
        self.grad_clip = grad_clip
        self.best_val_auc = 0.0
        self.epochs_no_improve = 0
        self.history: List[Dict] = []
        self.checkpoint_dir = "checkpoints"
        self.metadata = metadata           # ← graph (node_types, edge_types) tuple
        os.makedirs(self.checkpoint_dir, exist_ok=True)

    def train_epoch(self, data_loader):
        self.model.train()
        total_loss = 0
        for batch in data_loader:
            self.optimizer.zero_grad()
            x_dict = {k: v.to(self.device) for k, v in batch.x_dict.items()}
            edge_index_dict = {k: v.to(self.device) for k, v in batch.edge_index_dict.items()}
            src_nodes = batch.src_nodes.to(self.device)
            dst_nodes = batch.dst_nodes.to(self.device)
            labels = batch.labels.to(self.device)

            logits = self.model(x_dict, edge_index_dict, src_nodes, dst_nodes, batch.src_type, batch.dst_type)
            loss = F.binary_cross_entropy_with_logits(logits, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.grad_clip)
            self.optimizer.step()
            total_loss += loss.item()
        return total_loss / len(data_loader)

    @torch.no_grad()
    def evaluate(self, data_loader):
        self.model.eval()
        all_labels = []
        all_scores = []
        for batch in data_loader:
            x_dict = {k: v.to(self.device) for k, v in batch.x_dict.items()}
            edge_index_dict = {k: v.to(self.device) for k, v in batch.edge_index_dict.items()}
            src_nodes = batch.src_nodes.to(self.device)
            dst_nodes = batch.dst_nodes.to(self.device)
            labels = batch.labels.cpu().numpy()

            logits = self.model(x_dict, edge_index_dict, src_nodes, dst_nodes, batch.src_type, batch.dst_type)
            scores = torch.sigmoid(logits).cpu().numpy()
            all_labels.extend(labels)
            all_scores.extend(scores)

        metrics = evaluate_all(np.array(all_labels), np.array(all_scores))
        return metrics

    @torch.no_grad()
    def evaluate_ranking_per_disease(
        self,
        data,
        edge_index_dict: Dict,
        test_pos,
        all_pos,
        n_drug: int,
        k_list=(10, 20),
    ):
        """
        Proper link-prediction ranking evaluation, done per disease
        ("tail corruption", the standard KG-completion protocol):

        For each disease that has at least one held-out test edge, score
        EVERY drug against that disease (not just the ones in the test
        batch), filter out drug-disease pairs that are known positives from
        ANY split (so the model isn't penalized for correctly ranking a
        true-but-different-split edge above the one test edge — the
        "filtered" setting from Bordes et al. 2013), then rank each true
        test drug among the remaining candidates.

        This replaces the flat, batch-level hits@k/ndcg@k in evaluate(),
        which only ranked within the small test batch itself (114 pos + 114
        neg pairs) and is capped at k/n_pos regardless of model quality —
        not what "hits@k" means in the link-prediction literature.

        Returns (macro_avg_metrics, per_disease_metrics) where
        per_disease_metrics is a list of (disease_idx, metrics_dict,
        n_test_edges) so results can be reported disease-by-disease as well
        as macro-averaged (each disease weighted equally, regardless of how
        many test edges it has).
        """
        self.model.eval()
        x_dict = {k: v.to(self.device) for k, v in data.x_dict.items()}
        ei_dict = {k: v.to(self.device) for k, v in edge_index_dict.items()}

        pos_by_disease: Dict[int, List[int]] = {}
        for drug, disease in test_pos:
            pos_by_disease.setdefault(disease, []).append(drug)

        all_drug_ids = torch.arange(n_drug, dtype=torch.long, device=self.device)
        per_disease_metrics = []

        for disease, true_drugs in sorted(pos_by_disease.items()):
            disease_batch = torch.full((n_drug,), disease, dtype=torch.long, device=self.device)
            logits = self.model(x_dict, ei_dict, all_drug_ids, disease_batch, "Drug", "Disease")
            scores = torch.sigmoid(logits).cpu().numpy()

            hits = {k: [] for k in k_list}
            ndcgs = {k: [] for k in k_list}
            reciprocal_ranks = []

            for true_drug in true_drugs:
                filtered_scores = scores.copy()
                for d in range(n_drug):
                    if d != true_drug and (d, disease) in all_pos:
                        filtered_scores[d] = -np.inf  # remove other known positives (filtered setting)

                order = np.argsort(-filtered_scores)
                rank = int(np.where(order == true_drug)[0][0]) + 1  # 1-indexed
                reciprocal_ranks.append(1.0 / rank)
                for k in k_list:
                    hits[k].append(1.0 if rank <= k else 0.0)
                    ndcgs[k].append(1.0 / np.log2(rank + 1) if rank <= k else 0.0)

            metrics = {"mrr": float(np.mean(reciprocal_ranks))}
            for k in k_list:
                metrics[f"hits@{k}"] = float(np.mean(hits[k]))
                metrics[f"ndcg@{k}"] = float(np.mean(ndcgs[k]))
            per_disease_metrics.append((disease, metrics, len(true_drugs)))

        macro: Dict[str, float] = {}
        if per_disease_metrics:
            for key in per_disease_metrics[0][1]:
                macro[key] = float(np.mean([m[key] for _, m, _ in per_disease_metrics]))

        return macro, per_disease_metrics

    def _flush_history(self):
        """Write history to disk after every epoch so /api/v1/training/history stays live."""
        history_path = os.path.join(self.checkpoint_dir, "training_history.json")
        with open(history_path, "w") as f:
            json.dump(self.history, f, indent=2)

    def fit(self, train_loader, val_loader):
        for epoch in range(1, self.max_epochs + 1):
            train_loss = self.train_epoch(train_loader)
            val_metrics = self.evaluate(val_loader)
            val_auc = val_metrics["roc_auc"]
            self.history.append({"epoch": epoch, "train_loss": train_loss, **val_metrics})
            self.scheduler.step()

            # ← write per-epoch so the frontend training tab can poll live progress
            self._flush_history()

            logger.info(f"Epoch {epoch}/{self.max_epochs} — loss: {train_loss:.4f} — val_auc: {val_auc:.4f}")

            if val_auc > self.best_val_auc:
                self.best_val_auc = val_auc
                self.epochs_no_improve = 0
                self.save_checkpoint("best_model.pt")
            else:
                self.epochs_no_improve += 1

            if epoch % 10 == 0:
                self.save_checkpoint(f"checkpoint_epoch_{epoch}.pt")

            if epoch >= self.min_epochs and self.epochs_no_improve >= self.patience:
                logger.info(f"Early stopping triggered at epoch {epoch}")
                break

        # Final flush (covers the last epoch if loop exited normally)
        self._flush_history()

    def save_checkpoint(self, filename: str):
        path = os.path.join(self.checkpoint_dir, filename)
        ckpt = {
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scheduler_state_dict": self.scheduler.state_dict(),
            "best_val_auc": self.best_val_auc,
        }
        # ── FIX: save graph topology so inference can verify it matches ──
        if self.metadata is not None:
            ckpt["metadata"] = self.metadata
        torch.save(ckpt, path)
        logger.info(f"Checkpoint saved: {path}")

    def load_checkpoint(self, filename: str):
        path = os.path.join(self.checkpoint_dir, filename)
        checkpoint = torch.load(path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        self.best_val_auc = checkpoint["best_val_auc"]
        if "metadata" in checkpoint:
            self.metadata = checkpoint["metadata"]
        logger.info(f"Checkpoint loaded: {path}")
