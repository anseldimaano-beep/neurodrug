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
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [hist, stat] = await Promise.all([
        apiClient.get<EpochRecord[]>("/training/history"),
        apiClient.get<TrainingStatus>("/training/status"),
      ]);
      setHistory(hist as unknown as EpochRecord[]);
      setStatus(stat as unknown as TrainingStatus);
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
    </div>
  );
}
