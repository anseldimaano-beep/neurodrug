"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import dynamic from "next/dynamic";

const Graph = dynamic(() => import("react-graph-vis"), { ssr: false });

interface Props { diseaseId?: string; }

const EDGE_COLOR: Record<string, string> = {
  DrugTarget:    "#00cec9",
  GeneDisease:   "#74b9ff",
  GeneGene:      "#a29bfe",
  ClinicalTrial: "#fd9644",
  DrugDisease:   "#ff6b81",
};
const EDGE_WIDTH: Record<string, number> = {
  DrugTarget: 1.5, GeneDisease: 1.5, ClinicalTrial: 1.25, DrugDisease: 1.25, GeneGene: 0.75,
};
const EDGE_OPACITY_DEFAULT = 0.28;
const GENE_RADIUS = 210;
const DRUG_RADIUS = 430;

const BG = "#080d17";

export default function KnowledgeGraphExplorer({ diseaseId = "MONDO_0018177" }: Props) {
  const [allNodes, setAllNodes]         = useState<any[]>([]);
  const [allEdges, setAllEdges]         = useState<any[]>([]);
  const [graphData, setGraphData]       = useState<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });
  const [loading, setLoading]           = useState(false);
  const [diseaseName, setDiseaseName]   = useState("");
  const [error, setError]               = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [filter, setFilter]             = useState<"all"|"Drug"|"Gene">("all");
  const [search, setSearch]             = useState("");
  const [nodeLimit, setNodeLimit]       = useState(40);
  const [activeEdgeTypes, setActiveEdgeTypes] = useState<Set<string>>(new Set(Object.keys(EDGE_COLOR)));
  const [isolateMode, setIsolateMode]   = useState(false);
  const networkRef   = useRef<any>(null);
  const diseaseIdRef = useRef<any>(null);
  const rawNodes     = useRef<any[]>([]);
  const rawEdges     = useRef<any[]>([]);
  const adjacencyRef = useRef<Map<any, any[]>>(new Map());
  const [searchInput, setSearchInput] = useState("");

  // Debounce search: typing updates searchInput instantly (snappy input box),
  // but the expensive filter+layout rebuild only fires 200ms after typing
  // pauses, instead of on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), 200);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => { if (diseaseId) fetchSubgraph(diseaseId); }, [diseaseId]);

  /* ── Fetch ─────────────────────────────────────────────────────────── */
  const fetchSubgraph = async (efoId: string) => {
    setLoading(true); setError(null); setSelectedNode(null);
    setSearchInput(""); setSearch(""); setFilter("all"); setIsolateMode(false);
    setActiveEdgeTypes(new Set(Object.keys(EDGE_COLOR)));
    try {
      const res = await fetch(
        `/api/v1/graph/subgraph?disease_efo_id=${efoId}&include_genes=true&include_drugs=true&depth=2`
      );
      if (!res.ok) throw new Error(`API ${res.status}`);
      const data = await res.json();
      setDiseaseName(data.disease?.name || efoId);
      diseaseIdRef.current = data.disease.id;

      // Build degree map + adjacency map in a single pass (adjacency lets
      // hover/select/isolate look up a node's neighbors in O(1) instead of
      // re-scanning all edges, which matters at 5000+ edges per disease).
      const degree: Record<any, number> = {};
      const adjacency = new Map<any, any[]>();
      const addAdj = (a: any, b: any) => {
        if (!adjacency.has(a)) adjacency.set(a, []);
        adjacency.get(a)!.push(b);
      };
      (data.edges || []).forEach((e: any) => {
        degree[e.source] = (degree[e.source] || 0) + 1;
        degree[e.target] = (degree[e.target] || 0) + 1;
        addAdj(e.source, e.target);
        addAdj(e.target, e.source);
      });
      adjacencyRef.current = adjacency;

      const edges = (data.edges || []).map((e: any) => ({
        from: e.source, to: e.target,
        _edgeType: e.edge_type || "",
        color: {
          color: EDGE_COLOR[e.edge_type] || "#4a4a6a",
          highlight: "#fdcb6e", hover: "#fdcb6e", opacity: EDGE_OPACITY_DEFAULT,
        },
        width: EDGE_WIDTH[e.edge_type] || 1,
        arrows: { to: { enabled: false } },
        smooth: false,
      }));

      const connectedIds = new Set<any>(edges.flatMap((e: any) => [e.from, e.to]));
      connectedIds.add(data.disease.id);

      const diseaseNode = {
        id:        data.disease.id,
        label:     data.disease.name,
        fullLabel: data.disease.name,
        nodeType:  "Disease",
        degree:    degree[data.disease.id] || 0,
        color: { background: "#ff4757", border: "#ff6b81", highlight: { background: "#ff7f8e", border: "#ffeaa7" } },
        shape: "star", size: 54,
        font: { size: 14, bold: true, color: "#fff", strokeWidth: 4, strokeColor: "#3d0000" },
        borderWidth: 3,
        shadow: { enabled: true, size: 22, x: 0, y: 0, color: "rgba(255,71,87,0.55)" },
        x: 0, y: 0, physics: false,
        title: `${data.disease.name} — Disease`,
        _raw: data.disease,
      };

      const others = data.nodes
        .filter((n: any) => connectedIds.has(n.id) && n.node_type !== "Disease")
        .map((n: any) => {
          const isDrug   = n.node_type === "Drug";
          const deg      = degree[n.id] || 1;
          const baseSize = isDrug ? 20 : 14;
          const size     = Math.min(baseSize + Math.sqrt(deg) * 3, isDrug ? 40 : 30);
          const label    = (n.name || "");
          // Only show label for higher-degree nodes to reduce clutter
          const showLabel = deg >= 3;
          return {
            id:        n.id,
            label:     showLabel ? (label.length > 16 ? label.slice(0, 16) + "…" : label) : "",
            fullLabel: label,
            nodeType:  n.node_type,
            degree:    deg,
            color: isDrug
              ? { background: "#00cec9", border: "#00b894", highlight: { background: "#55efc4", border: "#00b894" } }
              : { background: "#a29bfe", border: "#6c5ce7", highlight: { background: "#c7b9ff", border: "#6c5ce7" } },
            shape:    isDrug ? "diamond" : "ellipse",
            size,
            font: {
              size: Math.min(10 + Math.sqrt(deg), 14),
              color: "#e0e0f0",
              strokeWidth: 3,
              strokeColor: isDrug ? "#003d3b" : "#1a0a3d",
            },
            borderWidth: deg > 5 ? 2.5 : 1.5,
            shadow: {
              enabled: true, size: 8 + deg * 0.5, x: 0, y: 0,
              color: isDrug ? "rgba(0,206,201,0.35)" : "rgba(162,155,254,0.35)",
            },
            title: `${label} — ${isDrug ? "Drug" : "Gene"} • ${deg} connection${deg === 1 ? "" : "s"}`,
            _raw: n,
          };
        });

      rawNodes.current = [diseaseNode, ...others];
      rawEdges.current = edges;
      setAllNodes([diseaseNode, ...others]);
      setAllEdges(edges);
    } catch (err: any) {
      setError(err?.message ?? "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  /* ── Radial layout: deterministic, no physics ────────────────────────
     Disease starts at center. Genes and drugs each start in a ring, spaced by
     an ADAPTIVE radius that grows with node count (so circumference per
     node stays roughly constant instead of nodes/labels overlapping as
     the count climbs). Rings above STAGGER_THRESHOLD nodes are split
     into two interleaved bands (alternating inner/outer radius) so that
     angularly-adjacent nodes end up on different radii, doubling the
     effective spacing between neighboring labels.
     Drugs are additionally sorted by the angular position of the genes
     they target (circular mean), then spaced evenly in that sorted
     order -- so drugs sharing similar targets end up near each other
     without any two literally overlapping. */
  const applyRadialLayout = useCallback((disease: any, visibleNodes: any[], edges: any[]) => {
    const MIN_ARC_PER_NODE = 62;   // px of ring circumference reserved per node
    const STAGGER_THRESHOLD = 30;  // beyond this many nodes in a ring, use two bands
    const ringRadius = (count: number, base: number) =>
      Math.max(base, (count * MIN_ARC_PER_NODE) / (2 * Math.PI));

    const genes = visibleNodes.filter((n) => n.nodeType !== "Drug");
    const drugs = visibleNodes.filter((n) => n.nodeType === "Drug");

    genes.sort((a, b) => b.degree - a.degree);
    const geneAngle = new Map<any, number>();
    const nGenes = genes.length;
    const geneStagger = nGenes > STAGGER_THRESHOLD;
    const genePerBand = geneStagger ? Math.ceil(nGenes / 2) : nGenes;
    const geneRA = ringRadius(genePerBand, GENE_RADIUS);
    const geneRB = geneRA + 70;
    genes.forEach((g, i) => {
      const angle = (2 * Math.PI * i) / Math.max(nGenes, 1) - Math.PI / 2;
      geneAngle.set(g.id, angle); // angle only -- used below for drug targeting math
      const r = geneStagger && i % 2 === 1 ? geneRB : geneRA;
      g.x = Math.cos(angle) * r;
      g.y = Math.sin(angle) * r;
      g.physics = false;
    });

    const withAngle = drugs.map((d) => {
      const angles: number[] = [];
      edges.forEach((e) => {
        if (e.from === d.id && geneAngle.has(e.to))   angles.push(geneAngle.get(e.to)!);
        if (e.to   === d.id && geneAngle.has(e.from)) angles.push(geneAngle.get(e.from)!);
      });
      let angle: number | null = null;
      if (angles.length) {
        const sinSum = angles.reduce((s, a) => s + Math.sin(a), 0);
        const cosSum = angles.reduce((s, a) => s + Math.cos(a), 0);
        angle = Math.atan2(sinSum, cosSum);
      }
      return { d, angle };
    });
    withAngle.sort((a, b) => {
      if (a.angle === null && b.angle === null) return 0;
      if (a.angle === null) return 1;
      if (b.angle === null) return -1;
      return a.angle - b.angle;
    });

    // Sort drugs by their target-gene angle so drugs sharing similar
    // targets end up near each other, but then assign evenly-spaced final
    // angles in that sorted order -- using the raw computed angle directly
    // as the position causes drugs that share a popular target (e.g. EGFR)
    // to stack on top of each other instead of spreading around the ring.
    const nDrugs = withAngle.length;
    const drugStagger = nDrugs > STAGGER_THRESHOLD;
    const drugPerBand = drugStagger ? Math.ceil(nDrugs / 2) : nDrugs;
    const drugRA = ringRadius(drugPerBand, DRUG_RADIUS);
    const drugRB = drugRA + 110;
    withAngle.forEach((item, i) => {
      const angle = (2 * Math.PI * i) / Math.max(nDrugs, 1) - Math.PI / 2;
      const r = drugStagger && i % 2 === 1 ? drugRB : drugRA;
      item.d.x = Math.cos(angle) * r;
      item.d.y = Math.sin(angle) * r;
      item.d.physics = false;
    });

    if (disease) { disease.x = 0; disease.y = 0; }
  }, []);

  /* ── Build visible graph from current settings ─────────────────────── */
  const buildGraph = useCallback((
    nodes: any[], edges: any[],
    limit: number, f: string, s: string,
    edgeTypes: Set<string>, isolated: boolean, selId: any,
  ) => {
    // Sort by degree desc, always keep disease
    const disease = nodes.find((n) => n.nodeType === "Disease");
    const rest    = [...nodes.filter((n) => n.nodeType !== "Disease")]
      .sort((a, b) => b.degree - a.degree);

    // Filter by type + search
    let visible = rest.filter((n) =>
      (f === "all" || n.nodeType === f) &&
      (!s || n.fullLabel.toLowerCase().includes(s.toLowerCase()))
    ).slice(0, limit);

    // If isolate mode: only keep neighbors of selected
    if (isolated && selId) {
      const nbrs = new Set<any>([selId]);
      edges.forEach((e) => {
        if (e.from === selId) nbrs.add(e.to);
        if (e.to   === selId) nbrs.add(e.from);
      });
      visible = visible.filter((n) => nbrs.has(n.id));
    }

    const visibleIds = new Set([...(disease ? [disease.id] : []), ...visible.map((n) => n.id)]);

    const filteredEdges = edges.filter(
      (e) => visibleIds.has(e.from) && visibleIds.has(e.to) && edgeTypes.has(e._edgeType)
    );

    // Compute radial positions BEFORE building finalNodes below, so that
    // copies made for dimmed (search-mismatched) nodes pick up fresh x/y.
    if (!isolated) {
      applyRadialLayout(disease, visible, filteredEdges);
    }

    // Dim non-matching nodes (search)
    const finalNodes = [...(disease ? [disease] : []), ...visible].map((n) => {
      const matches = !s || n.fullLabel.toLowerCase().includes(s.toLowerCase()) || n.nodeType === "Disease";
      if (!matches) return {
        ...n,
        color: { background: "#1e2030", border: "#2d3158", highlight: n.color.highlight },
        font:  { ...n.font, color: "#3a3a5a" },
        shadow: { enabled: false },
      };
      return n;
    });

    return { nodes: finalNodes, edges: filteredEdges };
  }, [applyRadialLayout]);

  useEffect(() => {
    if (!allNodes.length) return;
    // Selection (highlightNeighbors) and isolate-mode view are both managed
    // by their own dedicated handlers below -- this effect intentionally
    // does not depend on selectedNode/isolateMode, otherwise every node
    // click or isolate-toggle would trigger a second full rebuild here that
    // immediately overwrites the more targeted update those handlers just
    // made (this was previously causing a visible flicker + wasted work on
    // every click, since 5000+ edges get re-filtered and the whole layout
    // gets recomputed on every render tied to selection).
    if (isolateMode) return;
    const g = buildGraph(allNodes, allEdges, nodeLimit, filter, search, activeEdgeTypes, false, undefined);
    setGraphData(g);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allNodes, allEdges, nodeLimit, filter, search, activeEdgeTypes]);

  /* ── Highlight neighbors on select ─────────────────────────────────── */
  const highlightNeighbors = useCallback((nodeId: any) => {
    const nbrs = new Set<any>([nodeId]);
    (adjacencyRef.current.get(nodeId) || []).forEach((nid: any) => nbrs.add(nid));
    setGraphData((g) => ({
      ...g,
      nodes: g.nodes.map((n) => nbrs.has(n.id) ? n : {
        ...n,
        color:  { background: "#141828", border: "#1e2240", highlight: n.color?.highlight },
        font:   { ...n.font, color: "#2a2a4a" },
        shadow: { enabled: false },
      }),
      edges: g.edges.map((e) =>
        (nbrs.has(e.from) && nbrs.has(e.to))
          ? { ...e, color: { ...e.color, opacity: 0.95 }, width: (EDGE_WIDTH[e._edgeType] || 1) + 1.5 }
          : { ...e, color: { ...e.color, color: "#1e2240", opacity: 0.15 }, width: 0.6 }
      ),
    }));
  }, []);

  /* ── Options ────────────────────────────────────────────────────────── */
  const options = useMemo(() => ({
    layout: { improvedLayout: false },
    physics: { enabled: false },
    nodes: { borderWidth: 2 },
    edges: { smooth: false, selectionWidth: 3 },
    interaction: {
      hover: true, zoomView: true, dragView: true, dragNodes: true,
      selectConnectedEdges: true, tooltipDelay: 60,
      keyboard: { enabled: true, bindToWindow: false },
      navigationButtons: false,
    },
    height: "620px",
  }), []);

  const events = useMemo(() => ({
    selectNode: ({ nodes: ids }: any) => {
      const n = allNodes.find((x) => x.id === ids[0]);
      setSelectedNode(n ?? null);
      if (n) highlightNeighbors(ids[0]);
    },
    deselectNode: () => {
      setSelectedNode(null);
      setIsolateMode(false);
      setGraphData(buildGraph(allNodes, allEdges, nodeLimit, filter, search, activeEdgeTypes, false, undefined));
    },
    doubleClick: ({ nodes: ids }: any) => {
      if (ids.length && networkRef.current)
        networkRef.current.focus(ids[0], { scale: 2.2, animation: { duration: 350 } });
    },
  }), [allNodes, allEdges, highlightNeighbors, buildGraph, nodeLimit, filter, search, activeEdgeTypes]);

  /* ── derived counts ─────────────────────────────────────────────────── */
  const totalDrugs = useMemo(() => allNodes.filter((n) => n.nodeType === "Drug").length, [allNodes]);
  const totalGenes = useMemo(() => allNodes.filter((n) => n.nodeType !== "Drug" && n.nodeType !== "Disease").length, [allNodes]);
  const visibleDrugs = useMemo(() => graphData.nodes.filter((n) => n.nodeType === "Drug").length, [graphData]);
  const visibleGenes = useMemo(() => graphData.nodes.filter((n) => n.nodeType !== "Drug" && n.nodeType !== "Disease").length, [graphData]);
  const edgeTypes    = useMemo(() => [...new Set(allEdges.map((e) => e._edgeType).filter(Boolean))], [allEdges]);

  const toggleEdgeType = (t: string) =>
    setActiveEdgeTypes((prev) => {
      const s = new Set(prev);
      s.has(t) ? s.delete(t) : s.add(t);
      return s;
    });

  /* ── Render ─────────────────────────────────────────────────────────── */
  return (
    <div className="flex flex-col gap-3">

      {/* ── Top stat bar ── */}
      {diseaseName && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-1">
          <div className="text-xs text-muted-foreground">
            <strong>{diseaseName}</strong>
            <span className="mx-2 opacity-30">|</span>
            showing <strong>{graphData.nodes.length}</strong> of {allNodes.length} nodes
            <span className="mx-2 opacity-30">·</span>
            <strong>{graphData.edges.length}</strong> of {allEdges.length} edges
          </div>
          <div className="flex items-center gap-3 text-xs font-medium">
            <LegendDot color="#ff4757" glow="rgba(255,71,87,0.6)" label="Disease" shape="circle" />
            <LegendDot color="#00cec9" glow="rgba(0,206,201,0.6)"  label={`Drugs (${visibleDrugs}/${totalDrugs})`} shape="diamond" />
            <LegendDot color="#a29bfe" glow="rgba(162,155,254,0.6)" label={`Genes (${visibleGenes}/${totalGenes})`} shape="ellipse" />
          </div>
        </div>
      )}

      {/* ── Controls row ── */}
      {allNodes.length > 1 && (
        <div className="flex flex-wrap items-center gap-2 px-1">
          {/* Node type filter */}
          {(["all","Drug","Gene"] as const).map((f) => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded-full text-xs border transition-colors ${
                filter === f ? "bg-blue-600 text-white border-blue-600" : "bg-white border-gray-300 hover:bg-gray-50"
              }`}>
              {f === "all" ? "All nodes" : f + "s"}
            </button>
          ))}

          {/* Node limit slider */}
          <div className="flex items-center gap-1.5 ml-1">
            <span className="text-[10px] text-muted-foreground whitespace-nowrap">Show top</span>
            <input type="range" min={20} max={Math.min(allNodes.length, 200)} step={10}
              value={nodeLimit}
              onChange={(e) => setNodeLimit(Number(e.target.value))}
              className="w-24 h-1 accent-blue-600 cursor-pointer"
            />
            <span className="text-[10px] font-mono w-8">{nodeLimit}</span>
          </div>

          {/* Edge type toggles */}
          <div className="flex items-center gap-1.5 flex-wrap ml-1">
            {edgeTypes.map((t) => {
              const active = activeEdgeTypes.has(t);
              return (
                <button key={t} onClick={() => toggleEdgeType(t)}
                  title={active ? `Hide ${t}` : `Show ${t}`}
                  className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] border transition-all"
                  style={{
                    borderColor: active ? EDGE_COLOR[t] : "#d1d5db",
                    color:       active ? EDGE_COLOR[t] : "#9ca3af",
                    background:  active ? `${EDGE_COLOR[t]}18` : "transparent",
                  }}>
                  <span className="w-4 h-0.5 rounded inline-block" style={{ background: active ? EDGE_COLOR[t] : "#d1d5db" }} />
                  {t}
                </button>
              );
            })}
          </div>

          {/* Search */}
          <div className="flex items-center gap-1 ml-auto">
            <input type="text" placeholder="Search nodes…" value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="border rounded-full px-3 py-1 text-xs w-40 focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            {searchInput && <button onClick={() => { setSearchInput(""); setSearch(""); }} className="text-xs text-muted-foreground hover:text-red-500">✕</button>}
          </div>
        </div>
      )}

      {/* ── States ── */}
      {loading && <Placeholder bg={BG}><Spin color="#00cec9" /><p className="text-sm text-cyan-300/70 mt-3">Loading knowledge graph…</p></Placeholder>}
      {!loading && error && <Placeholder bg={BG}><p className="text-sm text-red-400">Error: {error}</p></Placeholder>}
      {!loading && !error && allNodes.length <= 1 && (
        <Placeholder bg={BG}><p className="text-sm text-slate-500">No graph data — run ETL for this disease first.</p></Placeholder>
      )}

      {/* ── Graph canvas ── */}
      {!loading && !error && allNodes.length > 1 && (
        <div className="relative rounded-xl overflow-hidden"
          style={{ background: BG, height: 640, boxShadow: "inset 0 0 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.06)" }}>

          {/* Grid */}
          <div className="absolute inset-0 pointer-events-none" style={{
            backgroundImage: "linear-gradient(rgba(255,255,255,0.018) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.018) 1px,transparent 1px)",
            backgroundSize: "48px 48px",
          }} />

          {/* Control buttons */}
          <div className="absolute top-3 right-3 z-10 flex flex-col gap-1.5">
            {([
              { icon: "+",  title: "Zoom in",   fn: () => networkRef.current?.moveTo({ scale: (networkRef.current?.getScale()||1)*1.3, animation: true }) },
              { icon: "-",   title: "Zoom out",  fn: () => networkRef.current?.moveTo({ scale: (networkRef.current?.getScale()||1)/1.3, animation: true }) },
              { icon: "[ ]", title: "Fit all",   fn: () => networkRef.current?.fit({ animation: { duration: 500 } }) },
              { icon: "o",  title: "Re-centre", fn: () => networkRef.current?.focus(diseaseIdRef.current, { scale: 0.85, animation: { duration: 400 } }) },
            ] as const).map(({ icon, title, fn }) => (
              <button key={title} onClick={fn} title={title}
                className="w-8 h-8 rounded-lg text-sm font-bold transition-all active:scale-95 hover:text-white"
                style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", color: "#94a3b8" }}>
                {icon}
              </button>
            ))}
          </div>

          {/* Selected node panel */}
          {selectedNode && (
            <div className="absolute top-3 left-3 z-10 rounded-xl p-4 w-60 text-xs space-y-2"
              style={{ background: "rgba(10,14,26,0.92)", border: "1px solid rgba(255,255,255,0.1)", backdropFilter: "blur(16px)", boxShadow: "0 8px 32px rgba(0,0,0,0.5)" }}>
              {/* Header */}
              <div className="flex items-start gap-2">
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0 mt-0.5" style={{
                  background: selectedNode.nodeType === "Disease" ? "#ff4757" : selectedNode.nodeType === "Drug" ? "#00cec9" : "#a29bfe",
                  boxShadow: `0 0 8px ${selectedNode.nodeType === "Disease" ? "rgba(255,71,87,0.6)" : selectedNode.nodeType === "Drug" ? "rgba(0,206,201,0.6)" : "rgba(162,155,254,0.6)"}`,
                }} />
                <span className="font-semibold text-sm text-white leading-tight">{selectedNode.fullLabel}</span>
              </div>
              {/* Stats */}
              <div className="grid grid-cols-2 gap-y-1.5 border-t pt-2" style={{ borderColor: "rgba(255,255,255,0.08)" }}>
                <span className="text-slate-400">Type</span><span className="text-slate-200">{selectedNode.nodeType}</span>
                <span className="text-slate-400">Connections</span><span className="text-cyan-300 font-mono">{selectedNode.degree}</span>
                {selectedNode._raw?.chembl_id && (<><span className="text-slate-400">ChEMBL</span><span className="text-slate-300 font-mono text-[10px]">{selectedNode._raw.chembl_id}</span></>)}
                {selectedNode._raw?.hgnc_symbol && (<><span className="text-slate-400">Symbol</span><span className="text-slate-300 font-mono">{selectedNode._raw.hgnc_symbol}</span></>)}
                {selectedNode._raw?.score != null && (<><span className="text-slate-400">Score</span><span className="text-cyan-300 font-mono">{Number(selectedNode._raw.score).toFixed(3)}</span></>)}
              </div>
              {/* Isolate button */}
              <button onClick={() => {
                  const newMode = !isolateMode;
                  setIsolateMode(newMode);
                  if (newMode && selectedNode) {
                    const nid = selectedNode.id;
                    const visible = new Set(graphData.nodes.map((n: any) => n.id));
                    const nIds = new Set<any>([nid]);
                    (adjacencyRef.current.get(nid) || []).forEach((oid: any) => {
                      if (visible.has(oid)) nIds.add(oid);
                    });
                    const disNode = allNodes.find((n: any) => n.id === nid);
                    const nbrs = allNodes.filter((n: any) => nIds.has(n.id) && n.nodeType !== "Disease");
                    const fNodes = [disNode, ...nbrs.map((n: any, i: number) => {
                      const a = (2 * Math.PI * i) / Math.max(nbrs.length, 1) - Math.PI / 2;
                      const r = n.nodeType === "Drug" ? 350 : 500;
                      return { ...n, x: Math.cos(a) * r, y: Math.sin(a) * r, physics: false };
                    })].filter(Boolean);
                    const fEdges = allEdges.filter((e: any) => nIds.has(e.from) && nIds.has(e.to));
                    setGraphData({ nodes: fNodes, edges: fEdges });
                  } else {
                    setGraphData(buildGraph(allNodes, allEdges, nodeLimit, filter, search, activeEdgeTypes, false, undefined));
                  }
                }}
                className="w-full py-1.5 rounded-lg text-[11px] font-medium transition-all"
                style={{
                  background: isolateMode ? "rgba(0,206,201,0.15)" : "rgba(255,255,255,0.06)",
                  border: `1px solid ${isolateMode ? "rgba(0,206,201,0.4)" : "rgba(255,255,255,0.1)"}`,
                  color: isolateMode ? "#00cec9" : "#94a3b8",
                }}>
                {isolateMode ? "✓ Showing neighborhood" : "👁 Show only neighborhood"}
              </button>
              <p className="text-[10px] text-slate-600 border-t pt-1" style={{ borderColor: "rgba(255,255,255,0.06)" }}>
                Double-click to zoom · Esc to deselect
              </p>
            </div>
          )}

          <Graph
            key={`${diseaseId}-${nodeLimit}`}
            graph={graphData}
            options={options}
            events={events}
            getNetwork={(net: any) => {
              networkRef.current = net;
              // Paint dark background on every frame so vis.js canvas is dark
              net.on("beforeDrawing", (ctx: CanvasRenderingContext2D) => {
                ctx.save();
                ctx.setTransform(1, 0, 0, 1, 0, 0);
                ctx.fillStyle = BG;
                ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
                ctx.restore();
              });
              // Radial layout gives the initial positions, so fit immediately —
              // no physics settling to wait for.
              setTimeout(() => net.fit({ animation: false }), 0);
            }}
          />
        </div>
      )}
    </div>
  );
}

/* ── Small helpers ─────────────────────────────────────────────────────── */
function Placeholder({ bg, children }: { bg: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl flex flex-col items-center justify-center" style={{ background: bg, height: 640 }}>
      {children}
    </div>
  );
}

function Spin({ color }: { color: string }) {
  return <div className="animate-spin rounded-full h-10 w-10 border-b-2" style={{ borderColor: color }} />;
}

function LegendDot({ color, glow, label, shape }: { color: string; glow: string; label: string; shape: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block" style={{
        width: 12, height: 12,
        borderRadius: shape === "circle" ? "50%" : shape === "ellipse" ? "50%" : 0,
        transform: shape === "diamond" ? "rotate(45deg)" : undefined,
        background: color,
        boxShadow: `0 0 6px ${glow}`,
        flexShrink: 0,
      }} />
      {label}
    </span>
  );
}
