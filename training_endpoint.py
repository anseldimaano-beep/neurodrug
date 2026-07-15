from fastapi import APIRouter, HTTPException
from pathlib import Path
from typing import List, Dict, Any
import json

router = APIRouter()

HISTORY_PATH = Path("checkpoints/training_history.json")


@router.get("/history", response_model=List[Dict[str, Any]])
async def get_training_history():
    """Return per-epoch training history from checkpoints/training_history.json."""
    if not HISTORY_PATH.exists():
        return []
    try:
        with open(HISTORY_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(status_code=500, detail=f"Could not read training history: {e}")


@router.get("/status", response_model=Dict[str, Any])
async def get_training_status():
    """Return summary of last completed training run."""
    if not HISTORY_PATH.exists():
        return {"status": "idle", "epoch": 0, "best_auc": 0.0, "epochs_total": 0}
    try:
        with open(HISTORY_PATH) as f:
            history = json.load(f)
        if not history:
            return {"status": "idle", "epoch": 0, "best_auc": 0.0, "epochs_total": 0}
        last = history[-1]
        best_auc = max(h.get("roc_auc", 0.0) for h in history)
        return {
            "status": "idle",
            "epoch": last.get("epoch", 0),
            "train_loss": last.get("train_loss"),
            "roc_auc": last.get("roc_auc"),
            "best_auc": best_auc,
            "epochs_total": len(history),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
