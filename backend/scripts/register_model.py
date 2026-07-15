"""
register_model.py
-----------------
Run this once after a training run that crashed during MLflow model logging.
It registers the already-saved best_model.pt as the production checkpoint.

Usage:
    docker-compose exec api python scripts/register_model.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ml.registry import ModelRegistry
from app.core.logging import logger


def main():
    checkpoint = "checkpoints/best_model.pt"
    if not os.path.exists(checkpoint):
        raise FileNotFoundError(
            f"{checkpoint} not found — training must complete first."
        )

    registry = ModelRegistry()
    result = registry.register(
        name="NeuroDrugHGT",
        version="2.0.0",
        architecture="HGT",
        checkpoint_path=checkpoint,
        hyperparameters=dict(
            hidden_channels=256,
            num_layers=4,
            num_heads=8,
            lr=1e-3,
            max_epochs=100,
            patience=10,
        ),
        metrics=dict(
            epoch=14,
            train_loss=0.2839,
            roc_auc=0.9031,
        ),
        is_production=True,
    )

    logger.info(f"Registered: {result['name']} v{result['version']}")
    logger.info("Next: docker-compose exec api python scripts/seed_model_version.py")


if __name__ == "__main__":
    main()
