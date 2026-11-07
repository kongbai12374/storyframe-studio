from rest_framework import serializers
from .models import Script, Asset, Provider, CanvasProject, Job, Profile


class ScriptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Script
        fields = [
            "id",
            "title",
            "synopsis",
            "style",
            "scenes",
            "revision",
            "updated_at",
        ]
        read_only_fields = ["id", "revision", "updated_at"]


class AssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    def get_url(self, obj):
        return f"/api/assets/{obj.id}/file/"

    def get_thumbnail_url(self, obj):
        return f"/api/assets/{obj.id}/file/?thumbnail=1" if obj.thumbnail else ""

    class Meta:
        model = Asset
        fields = [
            "id",
            "name",
            "kind",
            "size",
            "metadata",
            "tags",
            "created_at",
            "url",
            "thumbnail_url",
        ]


class ProviderSerializer(serializers.ModelSerializer):
    key_hint = serializers.SerializerMethodField()

    def get_key_hint(self, obj):
        return "••••" + obj.key_tail

    class Meta:
        model = Provider
        fields = [
            "id",
            "name",
            "service",
            "base_url",
            "model",
            "active",
            "key_hint",
            "video_config",
        ]


class CanvasSerializer(serializers.ModelSerializer):
    latest_job_id = serializers.SerializerMethodField()

    def get_latest_job_id(self, obj):
        return (
            Job.objects.filter(
                user=obj.user, kind="canvas", snapshot__project_id=obj.id
            )
            .order_by("-id")
            .values_list("id", flat=True)
            .first()
        )

    class Meta:
        model = CanvasProject
        fields = [
            "id",
            "name",
            "revision",
            "schema_version",
            "document",
            "updated_at",
            "latest_job_id",
        ]
        read_only_fields = ["revision", "schema_version"]


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = [
            "id",
            "kind",
            "status",
            "stage",
            "progress",
            "result",
            "error",
            "error_code",
            "created_at",
            "started_at",
            "completed_at",
            "attempts",
        ]

    def to_representation(self, obj):
        d = super().to_representation(obj)
        d["remote_status"] = {
            k: v
            for k, v in obj.remote_state.items()
            if k in ["task_id", "status", "submission_state", "cancellation"]
        }
        d["node_statuses"] = {
            k: v.get("status", "submitting")
            for k, v in obj.remote_state.get("node_states", {}).items()
        }
        if obj.remote_state.get("flow"):
            d["budget_status"] = {
                "reserved_yuan": str(
                    sum(
                        __import__("decimal").Decimal(v)
                        for v in obj.remote_state.get("reservations", {}).values()
                    )
                ),
                "limit_yuan": obj.snapshot.get("budget", {}).get("limit_yuan"),
            }
        d["may_charge"] = obj.kind != "compose" or bool(obj.snapshot.get("use_tts"))
        d["result"] = {k: v for k, v in d["result"].items() if k != "path"}
        d["download_url"] = (
            f"/api/jobs/{obj.id}/download/"
            if obj.status == "succeeded" and obj.result.get("path")
            else None
        )
        return d
