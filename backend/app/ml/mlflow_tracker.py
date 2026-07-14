import os
import mlflow
from typing import Dict, Any, Optional
from app.core.config import settings
from app.core.logging import logger


class MLflowTracker:
    def __init__(self, experiment_name: str = "neurodrug_hgt", tracking_uri: Optional[str] = None):
        self.tracking_uri = tracking_uri or os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_experiment(experiment_name)
        self.run = None

    def start_run(self, run_name: str, params: Dict[str, Any]):
        self.run = mlflow.start_run(run_name=run_name)
        for key, value in params.items():
            mlflow.log_param(key, value)
        logger.info(f"MLflow run started: {run_name}")

    def log_metrics(self, metrics: Dict[str, float], step: int):
        for key, value in metrics.items():
            mlflow.log_metric(key, value, step=step)

    def log_model(self, model, artifact_path: str = "model"):
        mlflow.pytorch.log_model(model, artifact_path)

    def end_run(self):
        mlflow.end_run()
        logger.info("MLflow run ended")
