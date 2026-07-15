"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchPredictions } from "@/lib/api";
import { useEvidenceMap } from "@/hooks/use-evidence";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface Props {
  diseaseId?: string;
}

interface LiteratureItem {
  pubmed_id: string;
  title: string | null;
  journal: string | null;
  year: number | null;
  url: string;
}

interface ClinicalItem {
  trial_id: string;
  phase: string | null;
  status: string | null;
  url: string;
}

interface GeneLink {
  gene: string;
  url: string;
}

interface ValidationResult {
  prediction_id: number;
  literature: { evidence_count: number; items: LiteratureItem[] };
  clinical: { trial_count: number; items: ClinicalItem[] };
  biological: Record<string, any> & {
    target_gene_links?: GeneLink[];
    disease_gene_links?: GeneLink[];
  };
  total_evidence_count: number;
  errors?: Record<string, string>;
}

export function EvidenceValidation({ diseaseId = "" }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["predictions", diseaseId, 50],
    queryFn: () => fetchPredictions(diseaseId, 50),
  });

  // FIX C12: this tab used to trust a `rank` field straight from the API
  // (p.rank ?? idx + 1) without re-sorting, so ranks displayed out of
  // order (e.g. 2, 1, 3) whenever the stored rank fell out of sync with
  // the current prediction_score — which happens after re-training or
  // re-validation shifts scores slightly. Drug Predictions always
  // re-derived rank from a fresh sort; this tab now does the same, so
  // the two tabs can never disagree with each other again either.
  const predictions: any[] = (Array.isArray(data) ? [...data] : [])
    .sort((a, b) => (b.prediction_score ?? 0) - (a.prediction_score ?? 0))
    .map((p, idx) => ({ ...p, _rank: idx + 1 }));

  const predictionIds = predictions.map((p) => p.id).filter(Boolean);

  // FIX C9/C10: same shared cache as the Drug Predictions tab — this is
  // the SAME data, not a separate copy. Validation itself now runs via
  // `scripts/validate_all.py` rather than from the UI, so this tab is
  // read-only.
  const { data: evidenceMap = {} } = useEvidenceMap(diseaseId, predictionIds);

  const doneResults = Object.values(evidenceMap) as ValidationResult[];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Evidence Validation Center</CardTitle>
          <CardDescription>
            Cross-reference predictions against PubMed, ClinicalTrials.gov,
            and pathway databases. (Same evidence shown in the Drug
            Predictions tab — this view adds full source links and a
            validation summary. Run{" "}
            <code className="text-xs">scripts/validate_all.py</code> to
            populate/refresh evidence.)
          </CardDescription>
        </CardHeader>

        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">
              Loading predictions…
            </p>
          ) : predictions.length === 0 ? (
            <div className="rounded-md border border-dashed p-8 text-center">
              <p className="text-sm font-medium text-muted-foreground">
                No predictions available for this disease.
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Run the inference pipeline first, then return here to view
                validation evidence.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">Rank</TableHead>
                  <TableHead>Drug</TableHead>
                  <TableHead className="w-24">Score</TableHead>
                  <TableHead className="w-24">Status</TableHead>
                  <TableHead>Evidence</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {predictions.map((p: any) => {
                  const result: ValidationResult | undefined = evidenceMap[p.id];

                  return (
                    <TableRow key={p.id}>
                      {/* Rank — always the fresh sort position, never a stale stored value */}
                      <TableCell className="text-muted-foreground">
                        {p._rank}
                      </TableCell>

                      {/* Drug name */}
                      <TableCell className="font-medium">
                        {p.drug?.name ?? p.drug_name ?? "—"}
                        {p.drug?.chembl_id && (
                          <span className="ml-2 text-xs text-muted-foreground">
                            {p.drug.chembl_id}
                          </span>
                        )}
                      </TableCell>

                      {/* Score */}
                      <TableCell>
                        {typeof p.prediction_score === "number"
                          ? p.prediction_score.toFixed(4)
                          : "—"}
                      </TableCell>

                      {/* Prediction status badge */}
                      <TableCell>
                        <span
                          className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${
                            p.status === "validated"
                              ? "bg-green-100 text-green-800"
                              : "bg-yellow-100 text-yellow-800"
                          }`}
                        >
                          {p.status ?? "pending"}
                        </span>
                      </TableCell>

                      {/* Validation result */}
                      <TableCell>
                        {result ? (
                          <EvidenceSources result={result} />
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Summary card — only shown when at least one result exists */}
      {doneResults.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Validation Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <p className="text-2xl font-bold">{doneResults.length}</p>
                <p className="text-xs text-muted-foreground">Candidates validated</p>
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {doneResults.reduce((sum, r) => sum + (r.literature?.evidence_count ?? 0), 0)}
                </p>
                <p className="text-xs text-muted-foreground">Total literature hits</p>
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {doneResults.reduce((sum, r) => sum + (r.clinical?.trial_count ?? 0), 0)}
                </p>
                <p className="text-xs text-muted-foreground">Total clinical trials</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── evidence badges + expandable link list ─────────────────────────────────
function EvidenceSources({ result }: { result: ValidationResult }) {
  const litItems = result.literature?.items ?? [];
  const trialItems = result.clinical?.items ?? [];
  const targetGenes = result.biological?.target_gene_links ?? [];
  const errors = result.errors ?? {};
  const errorKeys = Object.keys(errors);

  const hasSources = litItems.length > 0 || trialItems.length > 0 || targetGenes.length > 0;

  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none flex-wrap gap-1.5">
        <Badge color="blue">📄 {result.literature?.evidence_count ?? 0} papers</Badge>
        <Badge color="purple">🏥 {result.clinical?.trial_count ?? 0} trials</Badge>
        <Badge color="green">🧬 {result.total_evidence_count ?? 0} total</Badge>
        {errorKeys.length > 0 && (
          <span
            title={errorKeys.map((k) => `${k}: ${errors[k]}`).join("\n")}
            className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-800"
          >
            ⚠ {errorKeys.join(", ")} failed
          </span>
        )}
        {hasSources && (
          <span className="text-xs text-muted-foreground group-open:hidden">▾ sources</span>
        )}
      </summary>

      <div className="mt-2 space-y-2 max-w-md">
        {litItems.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-muted-foreground">Literature</p>
            <ul className="mt-1 space-y-1">
              {litItems.map((it) => (
                <li key={it.pubmed_id} className="text-xs">
                  <a
                    href={it.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    {it.title ?? `PMID ${it.pubmed_id}`}
                  </a>
                  {(it.journal || it.year) && (
                    <span className="text-muted-foreground">
                      {" "}— {it.journal ?? ""} {it.year ?? ""}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {trialItems.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-muted-foreground">Clinical Trials</p>
            <ul className="mt-1 space-y-1">
              {trialItems.map((it) => (
                <li key={it.trial_id} className="text-xs">
                  <a
                    href={it.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-purple-600 hover:underline"
                  >
                    {it.trial_id}
                  </a>
                  {(it.phase || it.status) && (
                    <span className="text-muted-foreground">
                      {" "}— {[it.phase, it.status].filter(Boolean).join(", ")}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {targetGenes.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-muted-foreground">Shared Target Genes</p>
            <ul className="mt-1 flex flex-wrap gap-x-2 gap-y-1">
              {targetGenes.map((g) => (
                <li key={g.gene} className="text-xs">
                  <a
                    href={g.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-green-700 hover:underline"
                  >
                    {g.gene}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}

        {!hasSources && (
          <p className="text-xs text-muted-foreground">No supporting sources found.</p>
        )}
      </div>
    </details>
  );
}

// ── tiny inline badge helper ──────────────────────────────────────────────────
function Badge({
  children,
  color,
}: {
  children: React.ReactNode;
  color: "blue" | "purple" | "green";
}) {
  const styles = {
    blue:   "bg-blue-100 text-blue-800",
    purple: "bg-purple-100 text-purple-800",
    green:  "bg-green-100 text-green-800",
  };
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${styles[color]}`}
    >
      {children}
    </span>
  );
}

export default EvidenceValidation;
