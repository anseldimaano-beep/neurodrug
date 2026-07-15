"use client";

import { useEffect, useState, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiClient } from "@/lib/api";

interface EpochRecord {
  epoch: number;
  train_loss: number;
  roc_auc: number;
  average_precision?: number;
  hits_at_10?: number;
  mrr?: number;
  ndcg_at_10?: number;
}

interface TrainingStatus {
  status: string;
  epoch: number;
  best_auc: number;
  epochs_total: number;
  train_loss?: number;
  roc_auc?: number;
}

interface BenchmarkRow {
  model: string;
  type: string;
  roc_auc: number;
  average_precision: number;
  "hits@10": number;
  "hits@20"?: number;
  mrr: number;
  "ndcg@10": number;
  p_value_vs_hgt: number | null;
  "significant_at_0.05"?: boolean;
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardHeader className="pb-2 pt-4 px-4">
        <CardDescription className="text-xs uppercase tracking-wide">{label}</CardDescription>
        <CardTitle className="text-2xl font-mono">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}

export default function ModelTraining() {
  const [history, setHistory] = useState<EpochRecord[]>([]);
  const [status, setStatus] = useState<TrainingStatus | null>(null);
  const [benchmark, setBenchmark] = useState<BenchmarkRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [hist, stat, bench] = await Promise.all([
        apiClient.get<EpochRecord[]>("/training/history"),
        apiClient.get<TrainingStatus>("/training/status"),
        apiClient.get<BenchmarkRow[]>("/training/benchmark"),
      ]);
      setHistory(hist as unknown as EpochRecord[]);
      setStatus(stat as unknown as TrainingStatus);
      setBenchmark(bench as unknown as BenchmarkRow[]);
      setLastRefresh(new Date());
      setError(null);
    } catch (e: any) {
      const detail = e?.response?.data?.detail ?? e?.message ?? "Failed to load training data";
      setError(String(detail));
    }
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 3000);
    return () => clearInterval(id);
  }, [fetchData]);

  const fmt = (n?: number) => (n != null ? n.toFixed(4) : "—");

  return (
    <div className="space-y-4">
      {/* Status row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Best Val AUC" value={status ? fmt(status.best_auc) : "—"} />
        <StatCard label="Epochs" value={status ? String(status.epochs_total) : "—"} />
        <StatCard label="Last Loss" value={fmt(status?.train_loss)} />
        <StatCard label="Status" value={status?.status ?? "—"} />
      </div>

      {lastRefresh && (
        <p className="text-xs text-muted-foreground">
          Last updated {lastRefresh.toLocaleTimeString()} · polling every 3 s
        </p>
      )}

      {error && (
        <Card className="border-destructive">
          <CardContent className="pt-4">
            <p className="text-sm text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {history.length > 0 ? (
        <>
          {/* AUC chart */}
          <Card>
            <CardHeader>
              <CardTitle>Validation Metrics</CardTitle>
              <CardDescription>ROC-AUC and Average Precision per epoch</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={history} margin={{ top: 5, right: 24, left: 0, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis
                    dataKey="epoch"
                    label={{ value: "Epoch", position: "insideBottom", offset: -12, fontSize: 12 }}
                    tick={{ fontSize: 11 }}
                  />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => v.toFixed(4)} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line
                    type="monotone" dataKey="roc_auc" name="ROC-AUC"
                    stroke="#2563eb" dot={false} strokeWidth={2}
                  />
                  <Line
                    type="monotone" dataKey="average_precision" name="Avg Precision"
                    stroke="#16a34a" dot={false} strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Loss chart */}
          <Card>
            <CardHeader>
              <CardTitle>Training Loss</CardTitle>
              <CardDescription>Binary cross-entropy per epoch</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={history} margin={{ top: 5, right: 24, left: 0, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis
                    dataKey="epoch"
                    label={{ value: "Epoch", position: "insideBottom", offset: -12, fontSize: 12 }}
                    tick={{ fontSize: 11 }}
                  />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => v.toFixed(4)} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line
                    type="monotone" dataKey="train_loss" name="Train Loss"
                    stroke="#dc2626" dot={false} strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Ranking metrics */}
          <Card>
            <CardHeader>
              <CardTitle>Ranking Metrics</CardTitle>
              <CardDescription>Hits@10, MRR, and NDCG@10 per epoch</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={history} margin={{ top: 5, right: 24, left: 0, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis
                    dataKey="epoch"
                    label={{ value: "Epoch", position: "insideBottom", offset: -12, fontSize: 12 }}
                    tick={{ fontSize: 11 }}
                  />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => v.toFixed(4)} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line
                    type="monotone" dataKey="hits_at_10" name="Hits@10"
                    stroke="#7c3aed" dot={false} strokeWidth={2}
                  />
                  <Line
                    type="monotone" dataKey="mrr" name="MRR"
                    stroke="#ea580c" dot={false} strokeWidth={2}
                  />
                  <Line
                    type="monotone" dataKey="ndcg_at_10" name="NDCG@10"
                    stroke="#0891b2" dot={false} strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </>
      ) : (
        !error && (
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">
                No training history found. Run training first:
              </p>
              <code className="mt-2 block text-xs bg-muted rounded px-3 py-2 font-mono">
                docker compose exec api python scripts/run_training.py
              </code>
            </CardContent>
          </Card>
        )
      )}

      {/* Model comparison — HGT vs. baselines, from run_baselines.py */}
      {benchmark.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Model Comparison</CardTitle>
            <CardDescription>
              HGT vs. graph and traditional baselines, from{" "}
              <code className="text-xs">scripts/run_baselines.py</code>.
              "Sig." marks whether the difference from HGT is statistically
              significant (p &lt; 0.05).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                    <th className="py-2 pr-4">Model</th>
                    <th className="py-2 pr-4">Type</th>
                    <th className="py-2 pr-4">ROC AUC</th>
                    <th className="py-2 pr-4">AP</th>
                    <th className="py-2 pr-4">Hits@10</th>
                    <th className="py-2 pr-4">MRR</th>
                    <th className="py-2 pr-4">NDCG@10</th>
                    <th className="py-2 pr-4">p vs HGT</th>
                    <th className="py-2 pr-4">Sig.</th>
                  </tr>
                </thead>
                <tbody>
                  {benchmark.map((row) => {
                    const isHgt = row.model.toLowerCase().includes("hgt");
                    const isSignificant = row["significant_at_0.05"];
                    return (
                      <tr
                        key={row.model}
                        className={`border-b last:border-0 ${isHgt ? "bg-blue-50 font-semibold" : ""}`}
                      >
                        <td className="py-2 pr-4">{row.model}</td>
                        <td className="py-2 pr-4 text-muted-foreground">{row.type}</td>
                        <td className="py-2 pr-4 font-mono">{row.roc_auc.toFixed(4)}</td>
                        <td className="py-2 pr-4 font-mono">{row.average_precision.toFixed(4)}</td>
                        <td className="py-2 pr-4 font-mono">{row["hits@10"].toFixed(4)}</td>
                        <td className="py-2 pr-4 font-mono">{row.mrr.toFixed(4)}</td>
                        <td className="py-2 pr-4 font-mono">{row["ndcg@10"].toFixed(4)}</td>
                        <td className="py-2 pr-4 font-mono">
                          {row.p_value_vs_hgt == null ? "—" : row.p_value_vs_hgt.toFixed(4)}
                        </td>
                        <td className="py-2 pr-4">
                          {isHgt ? (
                            <span className="text-muted-foreground">n/a</span>
                          ) : (
                            <span
                              className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${
                                isSignificant
                                  ? "bg-green-100 text-green-800"
                                  : "bg-gray-100 text-gray-600"
                              }`}
                            >
                              {isSignificant ? "yes" : "no"}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {(() => {
              const hgt = benchmark.find((r) => r.model.toLowerCase().includes("hgt"));
              const beatenBy = hgt
                ? benchmark.filter(
                    (r) =>
                      !r.model.toLowerCase().includes("hgt") &&
                      r.roc_auc > hgt.roc_auc &&
                      r.p_value_vs_hgt != null &&
                      r.p_value_vs_hgt < 0.05
                  )
                : [];
              if (beatenBy.length > 0) {
                return (
                  <p className="mt-3 text-xs text-amber-700 bg-amber-50 rounded px-3 py-2">
                    ⚠ HGT is currently significantly outperformed on ROC AUC by:{" "}
                    {beatenBy.map((r) => r.model).join(", ")} (p &lt; 0.05). If this
                    checkpoint was trained before the leakage-guard fix, retrain
                    with <code>scripts/run_training.py</code> and re-run{" "}
                    <code>scripts/run_baselines.py</code> before treating this
                    as a real result.
                  </p>
                );
              }
              return null;
            })()}
          </CardContent>
        </Card>
      ) : (
        !error && (
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">
                No benchmark results found. Run the baseline comparison:
              </p>
              <code className="mt-2 block text-xs bg-muted rounded px-3 py-2 font-mono">
                docker compose exec api python scripts/run_baselines.py --epochs 60
              </code>
            </CardContent>
          </Card>
        )
      )}
    </div>
  );
}
