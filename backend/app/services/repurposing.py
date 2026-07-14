import torch
import numpy as np
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.domain import Drug, Disease, Prediction, ModelVersion, Gene, Interaction
from app.ml.predictor import DrugRepurposingPredictor
from app.ml.models.hgt import NeuroDrugHGT
from app.graph.builder import KnowledgeGraphBuilder
from app.graph.hetero_data import HeteroDataConverter
from app.ml.features import build_gene_features, build_drug_features, build_disease_features
from app.core.logging import logger


class DrugRepurposingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_inference(
        self,
        disease_efo_id: str,
        model_version_id: int,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        logger.info(f"Running drug repurposing inference for {disease_efo_id}")

        disease_result = await self.db.execute(
            select(Disease).where(Disease.efo_id == disease_efo_id)
        )
        disease = disease_result.scalar_one_or_none()
        if not disease:
            raise ValueError(f"Disease {disease_efo_id} not found")

        model_result = await self.db.execute(
            select(ModelVersion).where(ModelVersion.id == model_version_id)
        )
        model_version = model_result.scalar_one_or_none()
        if not model_version:
            raise ValueError(f"Model version {model_version_id} not found")

        # Build knowledge graph (uses ID-based lookups — no lazy loads)
        builder = KnowledgeGraphBuilder(self.db)
        nx_graph = await builder.build_from_database(disease_efo_ids=[disease_efo_id])

        nodes_by_type: Dict[str, List[Dict]] = {"Gene": [], "Drug": [], "Disease": []}
        node_index: Dict[str, Dict[str, int]] = {
            "Gene": {}, "Drug": {}, "Disease": {}
        }
        features_by_type: Dict[str, List[np.ndarray]] = {
            "Gene": [], "Drug": [], "Disease": []
        }

        for n, attr in nx_graph.nodes(data=True):
            nt = attr["node_type"]
            idx = len(nodes_by_type[nt])
            nodes_by_type[nt].append(
                {"id": n, "name": attr["name"], "entity_id": attr.get("entity_id")}
            )
            node_index[nt][n] = idx
            if nt == "Gene":
                features_by_type[nt].append(
                    build_gene_features(0.0, 0, 0, 0, 0.0, False, False)
                )
            elif nt == "Drug":
                features_by_type[nt].append(build_drug_features(False, 0, 0.0))
            else:
                features_by_type[nt].append(build_disease_features(0, 0.0))

        edges_by_type: Dict[Any, List] = {}
        for u, v, attr in nx_graph.edges(data=True):
            u_type = nx_graph.nodes[u]["node_type"]
            v_type = nx_graph.nodes[v]["node_type"]
            rel = attr.get("edge_type", "associates")
            key = (u_type, rel, v_type)
            edges_by_type.setdefault(key, []).append(
                (node_index[u_type][u], node_index[v_type][v])
            )

        np_features = {k: np.array(v, dtype=np.float32) for k, v in features_by_type.items()}
        converter = HeteroDataConverter(
            node_feature_dims={"Gene": 7, "Drug": 3, "Disease": 2}
        )
        hetero_data = converter.convert(nodes_by_type, edges_by_type, np_features)

        metadata = hetero_data.metadata()
        model = NeuroDrugHGT(
            metadata=metadata, hidden_channels=128, num_layers=3, num_heads=4
        )
        predictor = DrugRepurposingPredictor(model)
        predictor.load_checkpoint(model_version.checkpoint_path)   # C1 fix

        drug_nodes = torch.arange(len(nodes_by_type["Drug"]))
        disease_key = f"Disease:{disease.efo_id}"
        if disease_key not in node_index["Disease"]:
            raise ValueError(
                f"Disease node '{disease_key}' not found in graph. "
                "Ensure ETL has been run for this disease."
            )
        disease_nodes = torch.tensor([node_index["Disease"][disease_key]])
        drug_names = [n["name"] for n in nodes_by_type["Drug"]]

        x_dict = {k: hetero_data[k].x for k in hetero_data.node_types}
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

        # ------------------------------------------------------------------ #
        # FIX C2: Build a name→Drug mapping in one query so we never set      #
        # drug_id=None, which violates the NOT NULL constraint on              #
        # Prediction.drug_id.  Candidates whose drug name is not in the DB    #
        # are skipped with a warning rather than causing an IntegrityError     #
        # that rolls back the entire inference run.                            #
        # ------------------------------------------------------------------ #
        drug_names_needed = [r["drug_name"] for r in results]
        drugs_result = await self.db.execute(
            select(Drug).where(Drug.name.in_(drug_names_needed))
        )
        drug_map: Dict[str, Drug] = {
            d.name: d for d in drugs_result.scalars().all()
        }

        persisted = 0
        skipped = 0
        for rank, res in enumerate(results):
            drug = drug_map.get(res["drug_name"])
            if drug is None:
                logger.warning(
                    f"Drug '{res['drug_name']}' not found in DB — skipping prediction"
                )
                skipped += 1
                continue

            pred = Prediction(
                drug_id=drug.id,          # always a real int now
                disease_id=disease.id,
                model_version_id=model_version_id,
                prediction_score=res["prediction_score"],
                rank=rank + 1,
                status="pending",
            )
            self.db.add(pred)
            persisted += 1

        await self.db.commit()
        logger.info(
            f"Inference complete for {disease.name}: "
            f"{persisted} predictions saved, {skipped} candidates skipped (drug not in DB)"
        )
        return results
