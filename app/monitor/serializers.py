from rest_framework import serializers

from monitor.models import AlertChannel, Check, Incident, Site


class CheckSerializer(serializers.ModelSerializer):
    """Serializer for Check model."""

    class Meta:
        model = Check
        fields = ["id", "timestamp", "response_time_ms", "status_code", "is_up", "error_message"]
        read_only_fields = fields


class IncidentSerializer(serializers.ModelSerializer):
    """Serializer for Incident model."""

    duration_human = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = ["id", "started_at", "ended_at", "duration_seconds", "duration_human", "notes"]
        read_only_fields = ["id", "started_at", "ended_at", "duration_seconds", "duration_human"]

    def get_duration_human(self, obj: Incident) -> str | None:
        """Return human-readable duration string."""
        if obj.duration_seconds is None:
            return None
        hours, remainder = divmod(obj.duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"


class SiteSerializer(serializers.ModelSerializer):
    """Serializer for Site model."""

    current_status = serializers.CharField(read_only=True)
    uptime_24h_percent = serializers.FloatField(read_only=True)
    uptime_7d_percent = serializers.FloatField(read_only=True)
    avg_response_time_24h_ms = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Site
        fields = [
            "id",
            "name",
            "url",
            "check_interval_seconds",
            "timeout_seconds",
            "expected_status_code",
            "is_active",
            "created_at",
            "last_checked_at",
            "current_status",
            "uptime_24h_percent",
            "uptime_7d_percent",
            "avg_response_time_24h_ms",
        ]
        read_only_fields = ["id", "created_at", "last_checked_at"]

    def create(self, validated_data: dict) -> Site:
        """Create a new Site, associating it with the requesting user."""
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class AlertChannelSerializer(serializers.ModelSerializer):
    """Serializer for AlertChannel model."""

    class Meta:
        model = AlertChannel
        fields = ["id", "channel_type", "config", "is_active"]
        read_only_fields = ["id"]
