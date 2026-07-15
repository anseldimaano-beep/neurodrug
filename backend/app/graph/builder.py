import networkx as nx
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models.domain import Gene, Drug, Disease, Interaction
from app.core.logging import logger


class KnowledgeGraphBuilder:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.nx_graph = nx.MultiDiGraph()

    async def build_from_database(
        self, disease_efo_ids: Optional[List[str]] = None
    ) -> nx.MultiDiGraph:
        logger.info(f"Building KG (disease filter: {disease_efo_ids})")

        # -- Step 1: resolve disease DB ids ----------------------------------
        disease_db_ids: Optional[List[int]] = None
        disease_id_to_node: Dict[int, str] = {}

        disease_query = select(Disease).where(Disease.is_deleted == False).order_by(Disease.id)
        if disease_efo_ids:
            disease_query = disease_query.where(Disease.efo_id.in_(disease_efo_ids))
        diseases = (await self.db.execute(disease_query)).scalars().all()

        for dis in diseases:
            node_key = f"Disease:{dis.efo_id or dis.mondo_id or dis.name}"
            disease_id_to_node[dis.id] = node_key
            self.nx_graph.add_node(node_key, node_type="Disease", name=dis.name,
                                   entity_id=dis.id, features={"category": dis.category})

        if disease_efo_ids:
            disease_db_ids = list(disease_id_to_node.keys())

        # -- Step 2: load ONLY interactions relevant to these diseases --------
        inter_q = select(Interaction).where(Interaction.is_deleted == False).order_by(Interaction.id)
        if disease_db_ids is not None:
            inter_q = inter_q.where(
                or_(
                    Interaction.disease_id.in_(disease_db_ids),
                    Interaction.disease_id == None,
                )
            )
        interactions = (await self.db.execute(inter_q)).scalars().all()

        # -- Step 3: collect only the gene/drug ids actually used -------------
        needed_gene_ids: set = set()
        needed_drug_ids: set = set()
        for i in interactions:
            if i.source_gene_id: needed_gene_ids.add(i.source_gene_id)
            if i.target_gene_id: needed_gene_ids.add(i.target_gene_id)
            if i.drug_id:        needed_drug_ids.add(i.drug_id)

        # -- Step 4: load only those genes and drugs --------------------------
        gene_id_to_node: Dict[int, str] = {}
        if needed_gene_ids:
            genes = (await self.db.execute(
                select(Gene).where(Gene.id.in_(needed_gene_ids), Gene.is_deleted == False).order_by(Gene.id)
            )).scalars().all()
            for g in genes:
                node_key = f"Gene:{g.symbol}"
                gene_id_to_node[g.id] = node_key
                self.nx_graph.add_node(node_key, node_type="Gene", name=g.symbol,
                                       entity_id=g.id,
                                       features={"is_oncogene": g.is_oncogene,
                                                 "is_tumor_suppressor": g.is_tumor_suppressor})

        drug_id_to_node: Dict[int, str] = {}
        if needed_drug_ids:
            drugs = (await self.db.execute(
                select(Drug).where(Drug.id.in_(needed_drug_ids), Drug.is_deleted == False).order_by(Drug.id)
            )).scalars().all()
            for d in drugs:
                node_key = f"Drug:{d.name}"
                drug_id_to_node[d.id] = node_key
                self.nx_graph.add_node(node_key, node_type="Drug", name=d.name,
                                       entity_id=d.id,
                                       features={"approval_status": d.approval_status,
                                                 "max_phase": d.max_phase})

        # -- Step 5: add edges ------------------------------------------------
        for inter in interactions:
            src = self._resolve_source(inter, gene_id_to_node, drug_id_to_node)
            dst = self._resolve_target(inter, gene_id_to_node, drug_id_to_node, disease_id_to_node)
            if src and dst and src in self.nx_graph and dst in self.nx_graph:
                self.nx_graph.add_edge(src, dst,
                                       edge_type=inter.interaction_type,
                                       weight=inter.confidence_score or 1.0,
                                       evidence_score=inter.evidence_score,
                                       source_db=inter.source_database)

        logger.info(f"KG built: {self.nx_graph.number_of_nodes()} nodes, "
                    f"{self.nx_graph.number_of_edges()} edges")
        return self.nx_graph

    def _resolve_source(self, inter, gene_id_to_node, drug_id_to_node) -> Optional[str]:
        if inter.source_gene_id is not None:
            return gene_id_to_node.get(inter.source_gene_id)
        if inter.drug_id is not None:
            return drug_id_to_node.get(inter.drug_id)
        return None

    def _resolve_target(self, inter, gene_id_to_node, drug_id_to_node, disease_id_to_node) -> Optional[str]:
        if inter.target_gene_id is not None:
            return gene_id_to_node.get(inter.target_gene_id)
        if inter.interaction_type == "DrugTarget" and inter.drug_id is not None:
            return drug_id_to_node.get(inter.drug_id)
        if inter.disease_id is not None:
            return disease_id_to_node.get(inter.disease_id)
        if inter.drug_id is not None:
            return drug_id_to_node.get(inter.drug_id)
        return None

    def get_subgraph(self, center_node: str, hops: int = 2) -> nx.MultiDiGraph:
        nodes = {center_node}
        for _ in range(hops):
            frontier: set = set()
            for n in nodes:
                frontier.update(self.nx_graph.predecessors(n))
                frontier.update(self.nx_graph.successors(n))
            nodes.update(frontier)
        return self.nx_graph.subgraph(nodes).copy()

    def get_statistics(self) -> Dict[str, Any]:
        return {
            "num_nodes": self.nx_graph.number_of_nodes(),
            "num_edges": self.nx_graph.number_of_edges(),
            "density":   nx.density(self.nx_graph),
            "is_connected": nx.is_weakly_connected(self.nx_graph),
            "num_weakly_connected_components": nx.number_weakly_connected_components(self.nx_graph),
        }
