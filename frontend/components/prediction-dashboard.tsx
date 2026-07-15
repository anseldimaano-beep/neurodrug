"use client";

import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchPredictions } from "@/lib/api";
import { useEvidenceMap } from "@/hooks/use-evidence";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

const DISEASES = [
  { label: "All Diseases",    efoId: "" },
  { label: "Glioblastoma",    efoId: "MONDO_0018177" },
  { label: "Neuroblastoma",   efoId: "MONDO_0005072" },
  { label: "Ewing Sarcoma",   efoId: "MONDO_0012817" },
  { label: "Medulloblastoma", efoId: "MONDO_0007959" },
  { label: "Wilms Tumor",     efoId: "MONDO_0019004" },
];

interface Props { diseaseId?: string; }

export function PredictionDashboard({ diseaseId = "" }: Props) {
  const [selectedDisease, setSelectedDisease] = useState(diseaseId);

  useEffect(() => { setSelectedDisease(diseaseId); }, [diseaseId]);

  const { data, isLoading } = useQuery({
    queryKey: ["predictions", selectedDisease, 100],
    queryFn:  () => fetchPredictions(selectedDisease, 100),
  });

  // Rank is always derived from a fresh sort by score, never trusted from
  // a stored `rank` field — that's what caused ranks to show out of order
  // (e.g. 2, 1, 3) after re-training/re-validation shifted scores slightly
  // without the stored rank being recomputed to match.
  const predictions: any[] = (Array.isArray(data) ? [...data] : [])
    .sort((a, b) => (b.prediction_score ?? 0) - (a.prediction_score ?? 0))
    .map((p, idx) => ({ ...p, _rank: idx + 1 }));

  const predictionIds = predictions.map(p => p.id).filter(Boolean);

  // FIX C9: shared cache — pre-populated from already-persisted DB
  // evidence, and shared with the Evidence Validation tab. Surviving tab
  // switches and disease switches is now automatic; no local useState.
  // Validation itself now runs via `scripts/validate_all.py` rather than
  // from the UI, so this is read-only here.
  const { data: evidenceMap = {} } = useEvidenceMap(selectedDisease, predictionIds);

  const selectedLabel =
    DISEASES.find(d => d.efoId === selectedDisease)?.label ?? "All Diseases";

  // Renders "Lit: 3 / Trials: 1" as links out to the first PubMed / trial
  // source (if any), plus a hover tooltip listing every source found —
  // full per-item lists live in the Evidence Validation tab.
  const EvidenceCell = ({ vr }: { vr: any }) => {
    if (!vr) return <span>-</span>;
    const litItems    = vr.literature?.items ?? [];
    const trialItems  = vr.clinical?.items    ?? [];
    const targets     = vr.biological?.target_gene_links?.length ?? 0;
    const errors: Record<string, string> = vr.errors ?? {};
    const errorKeys = Object.keys(errors);

    const litTitle = litItems.map((i: any) => i.title ?? i.pubmed_id).join("\n") || undefined;
    const trialTitle = trialItems.map((i: any) => i.trial_id).join("\n") || undefined;

    return (
      <span className="space-x-2">
        {litItems.length > 0 ? (
          <a
            href={litItems[0].url}
            target="_blank"
            rel="noopener noreferrer"
            title={litTitle}
            className="text-blue-600 hover:underline"
          >
            Lit: {litItems.length}
          </a>
        ) : (
          <span>Lit: 0</span>
        )}
        {trialItems.length > 0 ? (
          <a
            href={trialItems[0].url}
            target="_blank"
            rel="noopener noreferrer"
            title={trialTitle}
            className="text-purple-600 hover:underline"
          >
            Trials: {trialItems.length}
          </a>
        ) : (
          <span>Trials: 0</span>
        )}
        {targets > 0 && <span>Targets: {targets}</span>}
        {errorKeys.length > 0 && (
          <span
            title={errorKeys.map(k => `${k}: ${errors[k]}`).join("\n")}
            className="text-amber-600"
          >
            ⚠ {errorKeys.join(", ")} failed
          </span>
        )}
      </span>
    );
  };

  const statusBadge = (p: any) => {
    const vr = evidenceMap[p.id];
    const status = p.status ?? "pending";
    const lit    = vr?.literature?.evidence_count ?? 0;
    const trials = vr?.clinical?.trial_count      ?? 0;
    const targets = vr?.biological?.overlap_count ?? 0;
    const derived = vr
      ? (lit > 0 || trials > 0 || targets > 0 ? "validated" : "novel")
      : status;
    const color =
      derived === "validated" ? "bg-green-100 text-green-800" :
      derived === "novel"     ? "bg-blue-100  text-blue-800"  :
                                "bg-yellow-100 text-yellow-800";
    return <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${color}`}>{derived}</span>;
  };

  return (
    <div className="space-y-4">
      {!diseaseId && (
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium">Filter by Disease:</label>
          <select
            className="border rounded px-3 py-1.5 text-sm bg-white dark:bg-gray-800"
            value={selectedDisease}
            onChange={e => setSelectedDisease(e.target.value)}
          >
            {DISEASES.map(d => (
              <option key={d.efoId} value={d.efoId}>{d.label}</option>
            ))}
          </select>
          <span className="text-xs text-gray-400">
            {predictions.length} result{predictions.length !== 1 ? "s" : ""}
          </span>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Drug Repurposing Candidates</CardTitle>
          <CardDescription>
            {selectedDisease
              ? `Ranked by HGT prediction score - ${selectedLabel}`
              : "All diseases - select one to filter"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading predictions...</p>
          ) : predictions.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No predictions found. Run the repurposing pipeline first.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">#</TableHead>
                  <TableHead>Drug</TableHead>
                  <TableHead>Disease</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Evidence</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {predictions.map((p: any) => (
                  <TableRow key={p.id}>
                    <TableCell className="text-gray-400 text-sm font-mono">{p._rank}</TableCell>
                    <TableCell className="font-medium">
                      {p.drug?.name ?? p.drug_name ?? "-"}
                      {p.drug?.chembl_id && (
                        <span className="ml-2 text-xs text-blue-400">{p.drug.chembl_id}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-gray-500">{p.disease?.name ?? "-"}</TableCell>
                    <TableCell className="font-mono text-sm">
                      {typeof p.prediction_score === "number" ? p.prediction_score.toFixed(4) : "-"}
                    </TableCell>
                    <TableCell>{statusBadge(p)}</TableCell>
                    <TableCell className="text-xs text-gray-500">
                      <EvidenceCell vr={evidenceMap[p.id]} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default PredictionDashboard;
