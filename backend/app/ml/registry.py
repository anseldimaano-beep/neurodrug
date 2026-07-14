import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.core.logging import logger


class ModelRegistry:
    def __init__(self, registry_path: str = "model_registry"):
        self.registry_path = registry_path
        os.makedirs(registry_path, exist_ok=True)

    def register(
        self,
        name: str,
        version: str,
        architecture: str,
        checkpoint_path: str,
        hyperparameters: Dict[str, Any],
        metrics: Dict[str, float],
        is_production: bool = False,
    ) -> Dict[str, Any]:
        entry = {
            "name": name,
            "version": version,
            "architecture": architecture,
            "checkpoint_path": checkpoint_path,
            "hyperparameters": hyperparameters,
            "performance_metrics": metrics,
            "registered_at": datetime.utcnow().isoformat(),
            "is_production": is_production,
        }
        path = os.path.join(self.registry_path, f"{name}_{version}.json")
        with open(path, "w") as f:
            json.dump(entry, f, indent=2)
        logger.info(f"Model registered: {name} v{version} at {path}")
        return entry

    def list_models(self, name: Optional[str] = None) -> List[Dict[str, Any]]:
        models = []
        for fname in os.listdir(self.registry_path):
            if fname.endswith(".json"):
                with open(os.path.join(self.registry_path, fname)) as f:
                    m = json.load(f)
                    if name is None or m["name"] == name:
                        models.append(m)
        return sorted(models, key=lambda x: x["registered_at"], reverse=True)

    def get_production_model(self, name: str) -> Optional[Dict[str, Any]]:
        models = self.list_models(name)
        for m in models:
            if m.get("is_production"):
                return m
        return models[0] if models else None
