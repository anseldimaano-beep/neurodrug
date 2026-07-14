"use client";

import { useState, useEffect } from 'react';
import Graph from 'react-graph-vis';

const DISEASES = {
  "Glioblastoma": "EFO_0000519",
  "Neuroblastoma": "EFO_0000621",
  "Medulloblastoma": "EFO_0002939",
  "Ewing Sarcoma": "EFO_0000174",
  "DIPG": "EFO_0005543"
};

export default function KnowledgeGraphExplorer() {
  const [activeDisease, setActiveDisease] = useState("Neuroblastoma");
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchSubgraph(DISEASES[activeDisease]);
  }, [activeDisease]);

  const fetchSubgraph = async (efoId: string) => {
    setLoading(true);
    try {
      const response = await fetch(
        `/api/v1/graph/subgraph?disease_efo_id=${efoId}&include_genes=true&include_drugs=true&depth=2`
      );
      const data = await response.json();
      
      // Transform to vis.js format
      const nodes = [
        {
          id: data.disease.id,
          label: data.disease.name,
          color: '#e74c3c', // Red for Disease
          shape: 'dot',
          size: 30
        },
        ...data.nodes.map((n: any) => ({
          id: n.id,
          label: n.name,
          color: n.type === 'Drug' ? '#2ecc71' : '#9b59b6', // Green=Drug, Purple=Gene
          shape: 'dot',
          size: n.type === 'Drug' ? 20 : 15
        }))
      ];
      
      const edges = data.edges.map((e: any) => ({
        from: e.source,
        to: e.target,
        label: e.type,
        arrows: 'to'
      }));
      
      setGraphData({ nodes, edges });
    } catch (error) {
      console.error("Failed to fetch subgraph:", error);
    } finally {
      setLoading(false);
    }
  };

  const options = {
    layout: { improvedLayout: true },
    physics: {
      stabilization: false,
      barnesHut: {
        gravitationalConstant: -2000,
        springConstant: 0.04
      }
    },
    nodes: { font: { size: 12 } }
  };

  return (
    <div>
      {/* Disease Tabs */}
      <div className="flex gap-2 mb-4">
        {Object.keys(DISEASES).map(disease => (
          <button
            key={disease}
            onClick={() => setActiveDisease(disease)}
            className={`px-4 py-2 rounded-lg ${
              activeDisease === disease
                ? 'bg-blue-600 text-white'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
            }`}
          >
            {disease}
          </button>
        ))}
      </div>

      {/* Graph */}
      {loading ? (
        <div className="h-[600px] flex items-center justify-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      ) : (
        <div className="h-[600px] border rounded-lg">
          <Graph
            key={activeDisease} // Force re-mount on disease change
            graph={graphData}
            options={options}
          />
        </div>
      )}
    </div>
  );
}