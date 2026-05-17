from prometheus_client import Counter, Gauge, Histogram

# Counter: tracks total checks by status
site_check_total = Counter(
    "site_check_total",
    "Total number of site checks performed",
    ["status"],  # up, down, error
)

# Histogram: tracks check duration in seconds
site_check_duration_seconds = Histogram(
    "site_check_duration_seconds",
    "Duration of site HTTP checks in seconds",
    buckets=[0.1, 0.3, 1, 3, 10, 30],
)

# Counter: tracks number of checks enqueued by dispatch
dispatch_checks_enqueued_total = Counter(
    "dispatch_checks_enqueued_total",
    "Total number of check tasks enqueued by dispatch_checks",
)

# Counter: tracks opened incidents
incidents_opened_total = Counter(
    "incidents_opened_total",
    "Total number of incidents opened",
)

# Counter: tracks closed incidents
incidents_closed_total = Counter(
    "incidents_closed_total",
    "Total number of incidents closed",
)

# Gauge: current open (unresolved) incidents
current_open_incidents = Gauge(
    "current_open_incidents",
    "Number of currently open (unresolved) incidents",
)

# Gauge: total active monitored sites
sites_active_total = Gauge(
    "sites_active_total",
    "Total number of active monitored sites",
)
