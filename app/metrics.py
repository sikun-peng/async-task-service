from prometheus_client import Counter
REQUEST_COUNT = Counter("api_requests_total", "Total API requests to /submit")
JOBS_PROCESSED = Counter("jobs_processed_total", "Total jobs processed, by status", ["status"])
