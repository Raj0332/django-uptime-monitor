"""Celery tasks for the uptime monitor."""
import time
from datetime import timedelta
from typing import Any

import requests
import structlog
from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from monitor.metrics import (
    current_open_incidents,
    dispatch_checks_enqueued_total,
    incidents_closed_total,
    incidents_opened_total,
    site_check_duration_seconds,
    site_check_total,
    sites_active_total,
)
from monitor.models import Check, Incident, Site

logger = structlog.get_logger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="monitor.tasks.check_site",
)
def check_site(self, site_id: int) -> dict[str, Any]:
    """Perform an HTTP check for the given site and record the result."""
    try:
        site = Site.objects.get(pk=site_id)
    except Site.DoesNotExist:
        logger.warning("check_site_site_not_found", site_id=site_id)
        return {"site_id": site_id, "skipped": True, "reason": "not_found"}

    if not site.is_active:
        logger.debug("check_site_skipped_inactive", site_id=site_id)
        return {"site_id": site_id, "skipped": True, "reason": "inactive"}

    response_time_ms: int | None = None
    status_code: int | None = None
    is_up: bool = False
    error_message: str = ""

    start = time.perf_counter()
    try:
        response = requests.get(
            site.url,
            timeout=site.timeout_seconds,
            allow_redirects=True,
            headers={"User-Agent": "UptimeMonitor/1.0"},
        )
        elapsed = time.perf_counter() - start
        response_time_ms = int(elapsed * 1000)
        status_code = response.status_code
        is_up = status_code == site.expected_status_code
    except requests.Timeout as exc:
        elapsed = time.perf_counter() - start
        response_time_ms = int(elapsed * 1000)
        is_up = False
        error_message = f"Timeout after {site.timeout_seconds}s: {exc}"
    except requests.ConnectionError as exc:
        is_up = False
        error_message = f"Connection error: {exc}"
    except requests.RequestException as exc:
        is_up = False
        error_message = str(exc)

    elapsed_total = time.perf_counter() - start

    # Persist check record
    Check.objects.create(
        site=site,
        response_time_ms=response_time_ms,
        status_code=status_code,
        is_up=is_up,
        error_message=error_message,
    )
    Site.objects.filter(pk=site_id).update(last_checked_at=timezone.now())

    # Update Prometheus metrics
    metric_status = "up" if is_up else ("error" if error_message else "down")
    site_check_total.labels(status=metric_status).inc()
    site_check_duration_seconds.observe(elapsed_total)

    logger.info(
        "check_completed",
        site_id=site_id,
        url=site.url,
        is_up=is_up,
        status_code=status_code,
        response_time_ms=response_time_ms,
        error_message=error_message or None,
    )

    detect_incident.delay(site_id)
    return {
        "site_id": site_id,
        "is_up": is_up,
        "response_time_ms": response_time_ms,
        "status_code": status_code,
    }


@shared_task(name="monitor.tasks.dispatch_checks")
def dispatch_checks() -> int:
    """Find all sites due for a check and enqueue check_site tasks."""
    now = timezone.now()
    due_sites = []
    for site in Site.objects.filter(is_active=True).iterator():
        if site.last_checked_at is None:
            due_sites.append(site)
        else:
            next_check = site.last_checked_at + timedelta(seconds=site.check_interval_seconds)
            if now >= next_check:
                due_sites.append(site)

    for site in due_sites:
        check_site.delay(site.id)

    count = len(due_sites)
    if count:
        dispatch_checks_enqueued_total.inc(count)
    logger.info("dispatch_checks_completed", enqueued=count)
    return count


@shared_task(name="monitor.tasks.detect_incident")
def detect_incident(site_id: int) -> dict[str, Any]:
    """Open or close an incident based on the last 3 checks for a site."""
    try:
        site = Site.objects.get(pk=site_id)
    except Site.DoesNotExist:
        return {"site_id": site_id, "action": "skipped", "reason": "not_found"}

    recent_checks = list(site.checks.order_by("-timestamp")[:3])
    if not recent_checks:
        return {"site_id": site_id, "action": "none"}

    latest_check = recent_checks[0]

    # Try to close an existing open incident if the latest check is up
    open_incident = Incident.objects.filter(site=site, ended_at__isnull=True).first()
    if latest_check.is_up and open_incident:
        open_incident.close(timezone.now())
        incidents_closed_total.inc()
        logger.info("incident_closed", site_id=site_id, incident_id=open_incident.id)
        return {"site_id": site_id, "action": "closed", "incident_id": open_incident.id}

    # Open a new incident if 3 consecutive failures and no existing open incident
    if (
        len(recent_checks) == 3
        and all(not c.is_up for c in recent_checks)
        and not open_incident
    ):
        oldest = recent_checks[-1]
        incident = Incident.objects.create(site=site, started_at=oldest.timestamp)
        incidents_opened_total.inc()
        logger.warning(
            "incident_opened",
            site_id=site_id,
            incident_id=incident.id,
            started_at=str(oldest.timestamp),
        )
        return {"site_id": site_id, "action": "opened", "incident_id": incident.id}

    return {"site_id": site_id, "action": "none"}


@shared_task(name="monitor.tasks.aggregate_daily_uptime")
def aggregate_daily_uptime() -> int:
    """Compute previous UTC day uptime % and avg latency for each active site, cache in Redis."""
    from django.db.models import Avg, Count, Q

    now = timezone.now()
    day_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    date_str = day_start.strftime("%Y-%m-%d")

    processed = 0
    for site in Site.objects.filter(is_active=True).iterator():
        qs = Check.objects.filter(site=site, timestamp__gte=day_start, timestamp__lt=day_end)
        agg = qs.aggregate(
            total=Count("id"),
            up_count=Count("id", filter=Q(is_up=True)),
            avg_rt=Avg("response_time_ms", filter=Q(is_up=True)),
        )
        total = agg["total"] or 0
        up_count = agg["up_count"] or 0
        uptime_pct = (up_count / total * 100) if total else 0.0
        avg_rt = int(agg["avg_rt"]) if agg["avg_rt"] else None

        cache_key = f"uptime:{site.id}:{date_str}"
        cache.set(
            cache_key,
            {"uptime_pct": uptime_pct, "avg_response_time_ms": avg_rt, "total_checks": total},
            timeout=60 * 60 * 24 * 35,  # 35 days
        )
        processed += 1

    logger.info("aggregate_daily_uptime_completed", date=date_str, sites_processed=processed)
    return processed


@shared_task(name="monitor.tasks.update_gauges_task")
def update_gauges_task() -> None:
    """Periodic task to refresh Prometheus gauge metrics."""
    open_count = Incident.objects.filter(ended_at__isnull=True).count()
    active_count = Site.objects.filter(is_active=True).count()
    current_open_incidents.set(open_count)
    sites_active_total.set(active_count)
    logger.debug(
        "gauges_updated", open_incidents=open_count, active_sites=active_count
    )
