import axios from "axios"

// On Render (or any host where frontend and backend are separate services),
// set NEXT_PUBLIC_API_URL to the backend's public URL, e.g.
// https://neurodrug-api.onrender.com — this must be set at BUILD time since
// Next.js inlines NEXT_PUBLIC_* vars into the client bundle.
//
// Falls back to the local Docker Compose defaults when NEXT_PUBLIC_API_URL
// is not set: browser -> localhost:8000 (port-mapped), server-side -> the
// "api" service name on the compose network.
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  (typeof window !== "undefined" ? "http://localhost:8000" : "http://api:8000")

export const apiClient = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { "Content-Type": "application/json" },
})

apiClient.interceptors.request.use(config => {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("token") : null
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

apiClient.interceptors.response.use(
  res => res.data,
  err => {
    if (err.response?.status === 401) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("token")
        window.location.href = "/login"
      }
    }
    return Promise.reject(err)
  }
)

// ------------------------------------------------------------------ //
// FIX C3: the backend GET /graph/subgraph expects `disease_id` as a  //
// query parameter, NOT a path segment.                                //
//   Before: /graph/subgraph/${encodeURIComponent(diseaseId)}          //
//   After:  /graph/subgraph?disease_id=<diseaseId>&hops=2             //
// ------------------------------------------------------------------ //
export const fetchGraphData = (diseaseId: string): Promise<any> =>
  apiClient.get("/graph/subgraph", { params: { disease_id: diseaseId, hops: 2 } })

export const fetchPredictions = (diseaseId: string, topK = 20): Promise<any> =>
  apiClient.get("/predictions/", { params: { disease_efo_id: diseaseId, limit: topK } })

export const api = {
  // Auth
  login: (email: string, password: string) =>
    apiClient.post(
      "/auth/login",
      new URLSearchParams({ username: email, password }),
      { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
    ),
  me: () => apiClient.get("/auth/me"),

  // Predictions
  listPredictions: (params?: Record<string, any>) =>
    apiClient.get("/predictions/", { params }),
  runRepurposing: (
    diseaseEfoId: string,
    modelVersionId: number,
    topK = 20
  ) =>
    apiClient.post("/predictions/run", {
      disease_efo_id: diseaseEfoId,
      model_version_id: modelVersionId,
      top_k: topK,
    }),

  // Graph — C3 fix applied here too
  getSubgraph: (nodeId: string, hops = 2) =>
    apiClient.get("/graph/subgraph", { params: { disease_id: nodeId, hops } }),
  getGraphStats: () => apiClient.get("/graph/stats"),

  // ETL
  triggerOpenTargets: (efoId: string) =>
    apiClient.post("/etl/ingest/opentargets", null, { params: { efo_id: efoId } }),
  listJobs: () => apiClient.get("/etl/jobs"),
  getJob: (id: number) => apiClient.get(`/etl/jobs/${id}`),

  // Validation — C4: now calls the /run endpoint added to the backend
  validatePrediction: (predictionId: number) =>
    apiClient.post("/validation/run", { prediction_id: predictionId }),

  // FIX C9: bulk-read already-persisted evidence (no external API calls,
  // so it's safe to call on every page load / tab switch).
  getBulkEvidence: (predictionIds: number[]) =>
    apiClient.get("/validation/bulk", {
      params: { prediction_ids: predictionIds.join(",") },
    }),

  // Health
  health: () => apiClient.get("/health"),
  ready: () => apiClient.get("/health/ready"),
}
