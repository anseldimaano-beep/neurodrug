from prometheus_client import Counter, Histogram, Gauge, Info

# API metrics
REQUEST_COUNT = Counter(
    "neurodrug_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "neurodrug_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
)
ACTIVE_REQUESTS = Gauge(
    "neurodrug_http_requests_active",
    "Active HTTP requests",
)

# ML metrics
PREDICTION_COUNT = Counter(
    "neurodrug_predictions_total",
    "Total drug repurposing predictions",
    ["model_version", "status"],
)
TRAINING_RUNS = Counter(
    "neurodrug_training_runs_total",
    "Total model training runs",
    ["status"],
)
MODEL_PERFORMANCE = Gauge(
    "neurodrug_model_roc_auc",
    "Model ROC-AUC on validation set",
    ["model_version"],
)

# ETL metrics
ETL_JOBS = Counter(
    "neurodrug_etl_jobs_total",
    "Total ETL jobs run",
    ["source", "status"],
)
ETL_RECORDS = Counter(
    "neurodrug_etl_records_processed_total",
    "Total records processed by ETL",
    ["source"],
)

# Graph metrics
GRAPH_NODES = Gauge("neurodrug_graph_nodes_total", "Total nodes in knowledge graph", ["node_type"])
GRAPH_EDGES = Gauge("neurodrug_graph_edges_total", "Total edges in knowledge graph", ["edge_type"])

# System info
BUILD_INFO = Info("neurodrug_build", "NeuroDrug build information")
