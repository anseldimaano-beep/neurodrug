"use client";
import { useState } from "react";
import { api } from "@/lib/api";

/*
 * FIX H2: The original page called:
 *   apiClient.get(`/validation/${predictionId}`)
 * which hits a route that does not exist in the backend.
 *
 * Fix: call api.validatePrediction(id) which POSTs to /validation/run
 * (added by the C4 fix in validation.py).  We store the result in local
 * state instead of using useQuery with enabled:false, which avoids the
 * stale-while-revalidate confusion and gives clearer loading feedback.
 */
export default function ValidationPage() {
  const [predictionId, setPredictionId] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleValidate = async () => {
    const id = parseInt(predictionId, 10);
    if (!Number.isFinite(id)) {
      setError("Please enter a valid integer prediction ID.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.validatePrediction(id);
      setResult(data);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ??
          err?.message ??
          "Validation request failed."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="container mx-auto py-8 px-4">
      <h1 className="text-3xl font-bold mb-8">Validation Center</h1>

      <div className="flex gap-4 mb-8">
        <input
          className="border rounded px-4 py-2 flex-1"
          placeholder="Enter prediction ID…"
          value={predictionId}
          onChange={(e) => setPredictionId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleValidate()}
        />
        <button
          className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
          onClick={handleValidate}
          disabled={loading || predictionId === ""}
        >
          {loading ? "Validating…" : "Validate"}
        </button>
      </div>

      {error && (
        <p className="text-red-600 mb-4 text-sm">{error}</p>
      )}

      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div className="border rounded p-4">
              <p className="text-sm text-gray-500">Literature evidence</p>
              <p className="text-2xl font-bold">
                {result.literature?.evidence_count ?? 0}
              </p>
            </div>
            <div className="border rounded p-4">
              <p className="text-sm text-gray-500">Clinical trials</p>
              <p className="text-2xl font-bold">
                {result.clinical?.trial_count ?? 0}
              </p>
            </div>
            <div className="border rounded p-4">
              <p className="text-sm text-gray-500">Total evidence</p>
              <p className="text-2xl font-bold">
                {result.total_evidence_count ?? 0}
              </p>
            </div>
          </div>

          <details className="border rounded p-4">
            <summary className="cursor-pointer text-sm text-gray-600">
              Raw response
            </summary>
            <pre className="mt-2 bg-gray-100 dark:bg-gray-800 p-4 rounded text-xs overflow-auto">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </main>
  );
}
