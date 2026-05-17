"""Views for the uptime monitor application."""
import time
from typing import Any

import structlog
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from monitor.forms import SignupForm, SiteForm
from monitor.models import Check, Incident, Site
from monitor.serializers import CheckSerializer, IncidentSerializer, SiteSerializer

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

_readyz_cache: dict[str, Any] = {"result": None, "ts": 0.0}
_READYZ_CACHE_TTL = 5.0


class HealthzView(View):
    """Liveness probe — no DB or Redis required."""

    def get(self, request: HttpRequest) -> JsonResponse:
        return JsonResponse({"status": "ok"})


class ReadyzView(View):
    """Readiness probe — checks Postgres and Redis connectivity."""

    def get(self, request: HttpRequest) -> JsonResponse:
        now = time.monotonic()
        if _readyz_cache["result"] and (now - _readyz_cache["ts"]) < _READYZ_CACHE_TTL:
            cached = _readyz_cache["result"]
            status_code = 200 if cached["status"] == "ready" else 503
            return JsonResponse(cached, status=status_code)

        checks: dict[str, Any] = {}

        # Check Postgres
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks["postgres"] = "ok"
        except Exception as exc:
            checks["postgres"] = str(exc)

        # Check Redis
        try:
            import redis as redis_lib
            from django.conf import settings

            r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=2)
            r.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = str(exc)

        all_ok = all(v == "ok" for v in checks.values())
        result = {
            "status": "ready" if all_ok else "degraded",
            "checks": checks,
        }
        _readyz_cache["result"] = result
        _readyz_cache["ts"] = now

        return JsonResponse(result, status=200 if all_ok else 503)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class SignupView(View):
    """User registration view."""

    template_name = "monitor/signup.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        form = SignupForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request: HttpRequest) -> HttpResponse:
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created successfully. Welcome!")
            return redirect("dashboard")
        return render(request, self.template_name, {"form": form})


# ---------------------------------------------------------------------------
# Dashboard & Site views
# ---------------------------------------------------------------------------


class DashboardView(LoginRequiredMixin, View):
    """Main dashboard showing all user's monitored sites."""

    template_name = "monitor/dashboard.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        sites = Site.objects.filter(user=request.user).order_by("name")
        if request.GET.get("partial") == "1":
            return render(request, "monitor/partials/sites_grid.html", {"sites": sites})
        return render(request, self.template_name, {"sites": sites})


class SiteCreateView(LoginRequiredMixin, View):
    """Create a new monitored site."""

    template_name = "monitor/site_form.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        form = SiteForm()
        return render(request, self.template_name, {"form": form, "action": "Add"})

    def post(self, request: HttpRequest) -> HttpResponse:
        form = SiteForm(request.POST)
        if form.is_valid():
            site = form.save(commit=False)
            site.user = request.user
            site.save()
            messages.success(request, f"Site '{site.name}' added successfully.")
            logger.info("site_created", site_id=site.id, user_id=request.user.id, url=site.url)
            return redirect("dashboard")
        return render(request, self.template_name, {"form": form, "action": "Add"})


class SiteDetailView(LoginRequiredMixin, View):
    """Detail view for a single monitored site."""

    template_name = "monitor/site_detail.html"

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        site = get_object_or_404(Site, pk=pk, user=request.user)
        recent_checks = site.checks.all()[:100]
        recent_incidents = site.incidents.all()[:10]
        return render(
            request,
            self.template_name,
            {
                "site": site,
                "recent_checks": recent_checks,
                "recent_incidents": recent_incidents,
            },
        )


class SiteCardView(LoginRequiredMixin, View):
    """HTMX partial view returning a single site card for live refresh."""

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        site = get_object_or_404(Site, pk=pk, user=request.user)
        return render(request, "monitor/partials/site_card.html", {"site": site})


class SiteDeleteView(LoginRequiredMixin, View):
    """Delete a monitored site."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        site = get_object_or_404(Site, pk=pk, user=request.user)
        name = site.name
        site.delete()
        messages.success(request, f"Site '{name}' deleted.")
        logger.info("site_deleted", site_id=pk, user_id=request.user.id)
        return redirect("dashboard")


class SiteToggleView(LoginRequiredMixin, View):
    """Toggle is_active on a site."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        site = get_object_or_404(Site, pk=pk, user=request.user)
        site.is_active = not site.is_active
        site.save(update_fields=["is_active"])
        status_word = "resumed" if site.is_active else "paused"
        messages.info(request, f"Site '{site.name}' {status_word}.")
        return redirect("dashboard")


# ---------------------------------------------------------------------------
# REST API ViewSets
# ---------------------------------------------------------------------------


class SiteViewSet(viewsets.ModelViewSet):
    """API ViewSet for Site CRUD operations."""

    serializer_class = SiteSerializer

    def get_queryset(self):
        return Site.objects.filter(user=self.request.user).order_by("name")

    def perform_create(self, serializer: SiteSerializer) -> None:
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get"], url_path="checks")
    def checks(self, request: HttpRequest, pk: int = None) -> Response:
        """Return paginated checks for a site."""
        site = self.get_object()
        qs = Check.objects.filter(site=site).order_by("-timestamp")
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = CheckSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = CheckSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="incidents")
    def incidents(self, request: HttpRequest, pk: int = None) -> Response:
        """Return incidents for a site."""
        site = self.get_object()
        qs = Incident.objects.filter(site=site).order_by("-started_at")
        serializer = IncidentSerializer(qs, many=True)
        return Response(serializer.data)
