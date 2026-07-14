"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchPredictions } from "@/lib/api";
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

export function PredictionDashboard({ diseaseId = "" }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["predictions", diseaseId],
    queryFn: () => fetchPredictions(diseaseId, 20),
  });

  /*
   * FIX H1: The backend GET /predictions returns a JSON array directly
   * (FastAPI serialises result.scalars().all()).  The previous accessor
   *   data?.predictions || []
   * always resolved to [] because `data` is the array itself, not an
   * object with a `predictions` key.
   *
   * Fix: use Array.isArray to guard the cast.
   */
  const predictions: any[] = Array.isArray(data) ? data : [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Top Drug Repurposing Candidates</CardTitle>
          <CardDescription>
            Ranked by HGT link prediction score
            {diseaseId ? ` for ${diseaseId.replace("_", " ")}` : ""}.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">
              Loading predictions…
            </p>
          ) : predictions.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No predictions available. Run the inference pipeline first.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Rank</TableHead>
                  <TableHead>Drug</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Novelty</TableHead>
                  <TableHead>Evidence</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {predictions.map((p: any, idx: number) => (
                  <TableRow key={p.id ?? idx}>
                    <TableCell>{p.rank ?? idx + 1}</TableCell>
                    <TableCell className="font-medium">
                      {p.drug_name ?? p.drug?.name ?? "—"}
                    </TableCell>
                    <TableCell>
                      {p.prediction_score?.toFixed(4) ?? "—"}
                    </TableCell>
                    <TableCell>
                      {p.confidence_score?.toFixed(4) ?? "—"}
                    </TableCell>
                    <TableCell>
                      {p.novelty_score?.toFixed(4) ?? "—"}
                    </TableCell>
                    <TableCell>
                      {p.evidence_score?.toFixed(4) ?? "—"}
                    </TableCell>
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
