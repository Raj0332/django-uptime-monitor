from django.contrib import admin

from monitor.models import AlertChannel, Check, Incident, Site


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    """Admin configuration for Site model."""

    list_display = ["name", "url", "user", "is_active", "last_checked_at", "current_status"]
    list_filter = ["is_active", "user"]
    search_fields = ["name", "url", "user__username"]
    readonly_fields = ["created_at", "last_checked_at"]


@admin.register(Check)
class CheckAdmin(admin.ModelAdmin):
    """Admin configuration for Check model."""

    list_display = ["site", "timestamp", "is_up", "status_code", "response_time_ms"]
    list_filter = ["is_up", "site"]
    search_fields = ["site__name", "site__url"]
    readonly_fields = ["timestamp"]


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    """Admin configuration for Incident model."""

    list_display = ["site", "started_at", "ended_at", "duration_seconds"]
    list_filter = ["site"]
    search_fields = ["site__name", "notes"]
    readonly_fields = ["started_at"]


@admin.register(AlertChannel)
class AlertChannelAdmin(admin.ModelAdmin):
    """Admin configuration for AlertChannel model."""

    list_display = ["user", "channel_type", "is_active"]
    list_filter = ["channel_type", "is_active"]
    search_fields = ["user__username"]
