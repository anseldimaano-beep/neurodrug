import torch
import numpy as np
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.domain import Drug, Disease, Prediction, ModelVersion, Gene, Interaction
from app.ml.predictor import DrugRepurposingPredictor
from app.ml.models.hgt import NeuroDrugHGT
from app.ml.graph_convert import nx_to_heterodata
from app.graph.builder import KnowledgeGraphBuilder
from app.graph.hetero_data import HeteroDataConverter
from app.ml.features import build_gene_features, build_drug_features, build_disease_features
from app.core.logging import logger

# ── FIX: disease one-hot mapping (must match run_training.py exactly) ───────
_MONDO_TO_IDX: Dict[str, int] = {
    "MONDO_0018177": 0,   # Glioblastoma Multiforme
    "MONDO_0005072": 1,   # Neuroblastoma
    "MONDO_0012817": 2,   # Ewing Sarcoma
    "MONDO_0007959": 3,   # Medulloblastoma
    "MONDO_0019004": 4,   # Wilms Tumor
}
_NAME_TO_IDX: Dict[str, int] = {
    "glioblastoma": 0,
    "neuroblastoma": 1,
    "ewing": 2,
    "medulloblastoma": 3,
    "wilms": 4,
}
_N_DISEASES = len(_MONDO_TO_IDX)
_FEAT_DIM = 16


def _disease_one_hot(node_key: str, attr: dict) -> np.ndarray:
    """
    Build the 16-dim disease feature vector matching run_training.py's
    _disease_feats().  Searches node_key and attr values for MONDO IDs,
    then falls back to name-based matching.
    """
    one_hot = [0.0] * _N_DISEASES
    searchable = str(node_key) + " " + " ".join(str(v) for v in attr.values() if v)
    for mondo_id, idx in _MONDO_TO_IDX.items():
        if mondo_id in searchable:
            one_hot[idx] = 1.0
            return np.array(one_hot + [0.0] * (_FEAT_DIM - _N_DISEASES), dtype=np.float32)
    name = (attr.get("name") or "").lower()
    for keyword, idx in _NAME_TO_IDX.items():
        if keyword in name:
            one_hot[idx] = 1.0
            return np.array(one_hot + [0.0] * (_FEAT_DIM - _N_DISEASES), dtype=np.float32)
    logger.warning(f"_disease_one_hot: unrecognised disease node '{node_key}'")
    return np.array(one_hot + [0.0] * (_FEAT_DIM - _N_DISEASES), dtype=np.float32)


class DrugRepurposingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_inference(
        self,
        disease_efo_id: Optional[str],
        disease_mondo_id: Optional[str],
        model_version_id: int,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        logger.info(f"Running drug repurposing inference for {disease_efo_id}")

        if disease_mondo_id:
            disease_result = await self.db.execute(
                select(Disease).where(Disease.mondo_id == disease_mondo_id)
            )
            disease = disease_result.scalar_one_or_none()
            if not disease:
                raise ValueError(f"Disease with MONDO ID {disease_mondo_id} not found")
        else:
            disease_result = await self.db.execute(
                select(Disease).where(Disease.efo_id == disease_efo_id)
            )
            disease = disease_result.scalar_one_or_none()
            if not disease:
                raise ValueError(f"Disease with EFO ID {disease_efo_id} not found")

        model_result = await self.db.execute(
            select(ModelVersion).where(ModelVersion.id == model_version_id)
        )
        model_version = model_result.scalar_one_or_none()
        if not model_version:
            raise ValueError(f"Model version {model_version_id} not found")

        # Build knowledge graph — full graph, matches training topology
        builder = KnowledgeGraphBuilder(self.db)
        nx_graph = await builder.build_from_database()

        # ── Convert graph (identical pipeline to run_training.py) ─────────
        # nx_to_heterodata adds reverse edges and uses the same feature
        # functions as training, guaranteeing that metadata() matches the
        # checkpoint and every weight in k_rel / v_rel loads without
        # shape mismatches.
        hetero_data, node_lists = nx_to_heterodata(nx_graph)

        full_drug_list = node_lists.get("Drug", [])
        disease_list   = node_lists.get("Disease", [])

        # ── Filter: only rank real chemical drugs (have a chembl_id in DB) ──
        # ClinicalTrials ETL can ingest non-drug interventions ("Questionnaire",
        # "fecal microbiome", etc.) as Drug rows.  Restricting to chembl_id-bearing
        # drugs ensures the predictor only scores actual small molecules / biologics.
        _chembl_result = await self.db.execute(
            select(Drug.name).where(Drug.chembl_id.isnot(None))
        )
        _valid_drug_names = {row[0] for row in _chembl_result.fetchall()}
        if _valid_drug_names:
            drug_list = [dk for dk in full_drug_list if nx_graph.nodes[dk].get("name", "") in _valid_drug_names]
        else:
            drug_list = full_drug_list

        # FIX C7 (critical): drug_nodes must index into emb_dict["Drug"], whose
        # row order matches `full_drug_list` (the UNFILTERED node list — the
        # same order nx_to_heterodata used to build hetero_data['Drug'].x).
        # The previous code used torch.arange(len(drug_list)) — i.e. positions
        # 0..n-1 *within the filtered list* — and used that directly as the
        # row index into the full embedding tensor. Any time the filter
        # dropped even one earlier entry (e.g. a non-chembl ClinicalTrials
        # intervention), every later drug's score was silently computed from
        # an unrelated node's embedding. This affected every prediction, not
        # just the ones that happened to land on a near-zero row.
        _orig_index  = {key: i for i, key in enumerate(full_drug_list)}
        drug_indices = [_orig_index[dk] for dk in drug_list]

        n_drug       = len(drug_list)
        drug_names   = [nx_graph.nodes[k].get("name", k) for k in drug_list]

        disease_key = f"Disease:{disease.efo_id}"
        if disease_key not in disease_list:
            raise ValueError(
                f"Disease node '{disease_key}' not found in graph. "
                "Ensure ETL has been run for this disease."
            )
        disease_idx = disease_list.index(disease_key)

        # ── Initialise model with same metadata as training ───────────────
        model = NeuroDrugHGT(
            metadata=hetero_data.metadata(),
            hidden_channels=128,
            num_layers=2,
            num_heads=4,
        )
        predictor = DrugRepurposingPredictor(model)

        # ── Warmup: materialize PyG lazy Linear params before checkpoint ──
        # Linear(-1, out) uses UninitializedParameter; .shape raises
        # RuntimeError so load_checkpoint skips lin_dict keys entirely,
        # leaving node projection layers at random init. One encode() pass
        # first forces lazy init to the correct shape (hidden_channels x 16)
        # so the checkpoint weights load cleanly on the next call.
        with torch.no_grad():
            _wx = {k: hetero_data[k].x.to(predictor.device)
                   for k in hetero_data.node_types}
            _we = {k: hetero_data[k].edge_index.to(predictor.device)
                   for k in hetero_data.edge_types}
            model.encode(_wx, _we)

        predictor.load_checkpoint(model_version.checkpoint_path)

        drug_nodes    = torch.tensor(drug_indices, dtype=torch.long)
        disease_nodes = torch.tensor([disease_idx])

        x_dict          = {k: hetero_data[k].x          for k in hetero_data.node_types}
        edge_index_dict = {k: hetero_data[k].edge_index for k in hetero_data.edge_types}

        results = predictor.rank_candidates(
            x_dict,
            edge_index_dict,
            drug_nodes,
            disease_nodes,
            drug_names,
            disease.name,
            top_k=top_k,
        )

        drug_names_needed = [r["drug_name"] for r in results]
        drugs_result = await self.db.execute(
            select(Drug).where(Drug.name.in_(drug_names_needed))
        )
        drug_map: Dict[str, Drug] = {d.name: d for d in drugs_result.scalars().all()}

        persisted = 0
        skipped = 0
        for rank, res in enumerate(results):
            drug = drug_map.get(res["drug_name"])
            if drug is None:
                logger.warning(f"Drug '{res['drug_name']}' not found in DB — skipping")
                skipped += 1
                continue

            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(Prediction).values(
                drug_id=drug.id,
                disease_id=disease.id,
                model_version_id=model_version_id,
                prediction_score=res["prediction_score"],
                rank=rank + 1,
                status="pending",
                version=1,
                is_deleted=False,
            ).on_conflict_do_update(
                constraint="uq_predictions_drug_disease_model",
                set_=dict(
                    prediction_score=res["prediction_score"],
                    rank=rank + 1,
                    status="pending",
                ),
            )
            await self.db.execute(stmt)
            persisted += 1

        await self.db.commit()
        logger.info(
            f"Inference complete for {disease.name}: "
            f"{persisted} predictions saved, {skipped} candidates skipped"
        )
        return results



