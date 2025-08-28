from prometheus_client import Counter
from .models import JobStatus

# Count requests to job submission endpoint
REQUEST_COUNT = Counter(
    "api_requests_total",
    "Total API requests to /v1/jobs"
)

# Count jobs processed by final status (SUCCEEDED, FAILED, COMPENSATED, etc.)
JOBS_PROCESSED = Counter(
    "jobs_processed_total",
    "Total jobs processed, by status",
    ["status"]
)

# --- Pre-initialize counters so they appear as 0 in Prometheus ---
for status in [JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.COMPENSATED]:
    JOBS_PROCESSED.labels(status=status.value).inc(0)