"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

// FIX C9/C10: PredictionDashboard and EvidenceValidation each used to keep
// their own local useState for validation results. That meant:
//   1. Switching tabs (Radix TabsContent unmounts inactive tabs) wiped it.
//   2. Switching disease and back wiped it.
//   3. Validating in one tab was invisible in the other tab.
// Both problems have the same root cause: the results lived only in a
// component instance, not somewhere that outlives the component.
//
// This hook stores results in the app-wide React Query cache instead
// (query-provider.tsx wraps the whole app in a single QueryClient, so the
// cache itself outlives any individual component mount/unmount). The
// initial fill comes from GET /validation/bulk, which reads what's already
// saved in Postgres — no external API calls, so it's safe to call on every
// mount. Both components use the SAME queryKey, so they always agree.

export type EvidenceMap = Record<number, any>;

export function evidenceQueryKey(diseaseId: string) {
  return ["evidence-bulk", diseaseId || "all"];
}

export function useEvidenceMap(diseaseId: string, predictionIds: number[]) {
  return useQuery<EvidenceMap>({
    queryKey: evidenceQueryKey(diseaseId),
    queryFn: async () => {
      if (predictionIds.length === 0) return {};
      const res = await api.getBulkEvidence(predictionIds);
      // axios interceptor already unwraps to res.data; keys come back as
      // strings from JSON, normalize to numbers for lookup by p.id
      const map: EvidenceMap = {};
      for (const [k, v] of Object.entries(res ?? {})) {
        map[Number(k)] = v;
      }
      return map;
    },
    enabled: predictionIds.length > 0,
    staleTime: Infinity, // only changes via explicit validate, never goes stale on its own
    gcTime: Infinity,    // keep cached even if no component is currently subscribed
  });
}

export function useValidatePrediction(diseaseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (predictionId: number) => api.validatePrediction(predictionId),
    onSuccess: (result: any, predictionId: number) => {
      qc.setQueryData<EvidenceMap>(evidenceQueryKey(diseaseId), (old) => ({
        ...(old ?? {}),
        [predictionId]: result,
      }));
      // The prediction's own `status` field also gets updated server-side
      // during validation — refetch the predictions list so that shows up too.
      qc.invalidateQueries({ queryKey: ["predictions", diseaseId] });
    },
  });
}
