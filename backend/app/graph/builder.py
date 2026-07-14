import networkx as nx
from typing import Dict, List, Tuple, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.domain import Gene, Drug, Disease, Interaction, KnowledgeGraphNode, KnowledgeGraphEdge
from app.core.logging import logger


class KnowledgeGraphBuilder:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.nx_graph = nx.MultiDiGraph()

    async def build_from_database(
        self, disease_efo_ids: Optional[List[str]] = None
    ) -> nx.MultiDiGraph:
        logger.info("Building knowledge graph from database...")

        # ------------------------------------------------------------------ #
        # FIX C10: The previous version accessed inter.source_gene.symbol     #
        # and inter.target_gene.symbol inside _get_node_id/_get_target_node_id#
        # which are lazy-loaded relationships.  In an async SQLAlchemy        #
        # session that raises MissingGreenlet and crashes the graph build.     #
        #                                                                      #
        # Fix: build id→node_key lookup dicts for genes, drugs, and diseases  #
        # while loading those entities, then resolve interaction endpoints     #
        # purely by FK integer IDs without touching any relationship.          #
        # ------------------------------------------------------------------ #

        # --- Genes ---
        gene_result = await self.db.execute(
            select(Gene).where(Gene.is_deleted == False)
        )
        genes = gene_result.scalars().all()
        gene_id_to_node: Dict[int, str] = {}
        for g in genes:
            node_key = f"Gene:{g.symbol}"
            gene_id_to_node[g.id] = node_key
            self.nx_graph.add_node(
                node_key,
                node_type="Gene",
                name=g.symbol,
                entity_id=g.id,
                features={
                    "is_oncogene": g.is_oncogene,
                    "is_tumor_suppressor": g.is_tumor_suppressor,
                },
            )

        # --- Drugs ---
        drug_result = await self.db.execute(
            select(Drug).where(Drug.is_deleted == False)
        )
        drugs = drug_result.scalars().all()
        drug_id_to_node: Dict[int, str] = {}
        for d in drugs:
            node_key = f"Drug:{d.name}"
            drug_id_to_node[d.id] = node_key
            self.nx_graph.add_node(
                node_key,
                node_type="Drug",
                name=d.name,
                entity_id=d.id,
                features={
                    "approval_status": d.approval_status,
                    "max_phase": d.max_phase,
                },
            )

        # --- Diseases ---
        disease_query = select(Disease).where(Disease.is_deleted == False)
        if disease_efo_ids:
            disease_query = disease_query.where(Disease.efo_id.in_(disease_efo_ids))
        disease_result = await self.db.execute(disease_query)
        diseases = disease_result.scalars().all()
        disease_id_to_node: Dict[int, str] = {}
        for dis in diseases:
            node_key = f"Disease:{dis.efo_id or dis.name}"
            disease_id_to_node[dis.id] = node_key
            self.nx_graph.add_node(
                node_key,
                node_type="Disease",
                name=dis.name,
                entity_id=dis.id,
                features={"category": dis.category},
            )

        # --- Interactions (FILTERED by disease if disease_efo_ids provided) ---
        interaction_query = select(Interaction).where(Interaction.is_deleted == False)
        
        if disease_efo_ids:
            # Get database IDs for the filtered diseases
            disease_id_query = select(Disease.id).where(
                Disease.efo_id.in_(disease_efo_ids),
                Disease.is_deleted == False
            )
            disease_id_result = await self.db.execute(disease_id_query)
            disease_ids = [row[0] for row in disease_id_result.all()]
            
            # Only load interactions connected to these diseases
            interaction_query = interaction_query.where(
                Interaction.disease_id.in_(disease_ids)
            )
        
        interaction_result = await self.db.execute(interaction_query)
        interactions = interaction_result.scalars().all()
        for inter in interactions:
            src = self._resolve_source(inter, gene_id_to_node, drug_id_to_node)
            dst = self._resolve_target(inter, gene_id_to_node, disease_id_to_node)
            if src and dst and src in self.nx_graph and dst in self.nx_graph:
                self.nx_graph.add_edge(
                    src,
                    dst,
                    edge_type=inter.interaction_type,
                    weight=inter.confidence_score or 1.0,
                    evidence_score=inter.evidence_score,
                    source_db=inter.source_database,
                )

        logger.info(
            f"Graph built: {self.nx_graph.number_of_nodes()} nodes, "
            f"{self.nx_graph.number_of_edges()} edges"
        )
        return self.nx_graph

    # ------------------------------------------------------------------ #
    # ID-based resolvers — no lazy attribute access                        #
    # ------------------------------------------------------------------ #

    def _resolve_source(
        self,
        inter: Interaction,
        gene_id_to_node: Dict[int, str],
        drug_id_to_node: Dict[int, str],
    ) -> Optional[str]:
        if inter.source_gene_id is not None:
            return gene_id_to_node.get(inter.source_gene_id)
        if inter.drug_id is not None:
            return drug_id_to_node.get(inter.drug_id)
        return None

    def _resolve_target(
        self,
        inter: Interaction,
        gene_id_to_node: Dict[int, str],
        disease_id_to_node: Dict[int, str],
    ) -> Optional[str]:
        if inter.target_gene_id is not None:
            return gene_id_to_node.get(inter.target_gene_id)
        if inter.disease_id is not None:
            return disease_id_to_node.get(inter.disease_id)
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
            "density": nx.density(self.nx_graph),
            "is_connected": nx.is_weakly_connected(self.nx_graph),
            "num_weakly_connected_components": nx.number_weakly_connected_components(
                self.nx_graph
            ),
        }