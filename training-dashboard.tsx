"use client";

import { useEffect, useState, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { apiClient } from "@/lib/api";

interface EpochRow {
  epoch: number;
  train_loss: number;
  roc_auc: number;
  average_precision: number;
  hits_at_10?: number;
  "hits@10"?: number;
  "hits@20"?: number;
  mrr?: number;
}

interface HistoryResponse {
  epochs: EpochRow[];
  best_val_auc: number;
  total_epochs: number;
  is_training: boolean;
}

const POLL_MS = 3000;

export default function TrainingDashboard() {
  const [data, setData] = useState<HistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await apiClient.get<HistoryResponse>("/training/history");
      setData(res as unknown as HistoryResponse);
      setError(null);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to load training history");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
    const id = setInterval(fetchHistory, POLL_MS);
    return () => clearInterval(id);
  }, [fetchHistory]);

  const startTraining = async () => {
    setStarting(true);
    try {
      await apiClient.post("/training/start", {});
      await fetchHistory();
    } catch (e: any) {
      const detail = e?.response?.data?.detail ?? "Failed to start training";
      setError(detail);
    } finally {
      setStarting(false);
    }
  };

  // normalise hits@10 key name (trainer uses "hits@10", recharts needs no @)
  const chartData = (data?.epochs ?? []).map((e) => ({
    epoch: e.epoch,
    "Val AUC": +e.roc_auc.toFixed(4),
    "Train Loss": +e.train_loss.toFixed(4),
    "Avg Precision": +e.average_precision.toFixed(4),
  }));

  const isLive = data?.is_training ?? false;
  const bestAUC = data?.best_val_auc ?? 0;
  const totalEpochs = data?.total_epochs ?? 0;
  const lastEpoch = data?.epochs.at(-1);

  return (
    <div className="space-y-6">
      {/* ── header row ── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          {isLive ? (
            <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-600">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </span>
              Training in progress
            </span>
          ) : totalEpochs > 0 ? (
            <span className="text-xs text-muted-foreground">Last run · {totalEpochs} epochs</span>
          ) : null}
        </div>

        <button
          onClick={startTraining}
          disabled={starting || isLive}
          className="px-4 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground disabled:opacity-40 disabled:cursor-not-allowed hover:bg-primary/90 transition-colors"
        >
          {starting ? "Starting…" : isLive ? "Training…" : "Start Training"}
        </button>
      </div>

      {/* ── stat cards ── */}
      {totalEpochs > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "Best Val AUC", value: bestAUC.toFixed(4) },
            { label: "Epochs run", value: totalEpochs },
            { label: "Last loss", value: lastEpoch?.train_loss.toFixed(4) ?? "—" },
            { label: "Last val AUC", value: lastEpoch?.roc_auc.toFixed(4) ?? "—" },
          ].map(({ label, value }) => (
            <div key={label} className="rounded-lg border bg-muted/30 px-4 py-3">
              <p className="text-xs text-muted-foreground mb-0.5">{label}</p>
              <p className="text-xl font-semibold tabular-nums">{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* ── error ── */}
      {error && (
        <div className="text-sm text-destructive border border-destructive/30 bg-destructive/5 rounded-md px-4 py-2">
          {error}
        </div>
      )}

      {/* ── charts ── */}
      {loading && <p className="text-sm text-muted-foreground">Loading history…</p>}

      {!loading && totalEpochs === 0 && !error && (
        <div className="text-center py-12 text-sm text-muted-foreground">
          No training history yet. Click <strong>Start Training</strong> above,
          or run <code className="font-mono text-xs bg-muted px-1 rounded">docker-compose exec api python scripts/run_training.py</code> in your terminal.
        </div>
      )}

      {chartData.length > 0 && (
        <div className="space-y-6">
          {/* Val AUC */}
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
              Validation AUC & Average Precision
            </p>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                <XAxis dataKey="epoch" tick={{ fontSize: 11 }} label={{ value: "Epoch", position: "insideBottomRight", offset: -8, fontSize: 11 }} />
                <YAxis domain={[0, 1]} tick={{ fontSize: 11 }} tickFormatter={(v) => v.toFixed(2)} />
                <Tooltip formatter={(v: number) => v.toFixed(4)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="Val AUC" stroke="#3b82f6" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Avg Precision" stroke="#8b5cf6" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Train Loss */}
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
              Training Loss
            </p>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                <XAxis dataKey="epoch" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => v.toFixed(3)} />
                <Tooltip formatter={(v: number) => v.toFixed(4)} />
                <Line type="monotone" dataKey="Train Loss" stroke="#f59e0b" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* ── MLflow link ── */}
      {totalEpochs > 0 && (
        <p className="text-xs text-muted-foreground">
          Full experiment tracking →{" "}
          <a href="http://localhost:5000" target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-foreground">
            MLflow at localhost:5000
          </a>
        </p>
      )}
    </div>
  );
}
