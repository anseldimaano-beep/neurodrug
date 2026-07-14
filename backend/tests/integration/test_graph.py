import pytest
import networkx as nx
from app.graph.builder import KnowledgeGraphBuilder


class TestKnowledgeGraphBuilder:
    async def test_build_empty_graph(self, db_session):
        builder = KnowledgeGraphBuilder(db_session)
        graph = await builder.build_from_database()
        assert graph is not None
        assert isinstance(graph, nx.MultiDiGraph)

    async def test_get_statistics(self, db_session):
        builder = KnowledgeGraphBuilder(db_session)
        await builder.build_from_database()
        stats = builder.get_statistics()
        assert "num_nodes" in stats
        assert "num_edges" in stats
        assert "density" in stats

    async def test_subgraph_with_no_nodes(self, db_session):
        builder = KnowledgeGraphBuilder(db_session)
        await builder.build_from_database()
        # Non-existent center node returns empty or just that node
        subgraph = builder.get_subgraph("Gene:NONEXISTENT", hops=2)
        assert isinstance(subgraph, nx.MultiDiGraph)
