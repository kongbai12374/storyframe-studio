from django.db import models
from django.contrib.auth.models import User


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    quota_bytes = models.PositiveBigIntegerField(default=500 * 1024 * 1024)
    api_calls_remaining = models.PositiveIntegerField(default=100)


class Provider(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    service = models.CharField(
        max_length=10,
        choices=[
            ("llm", "LLM"),
            ("tts", "TTS"),
            ("video", "Video API"),
            ("image", "Image API"),
        ],
    )
    base_url = models.URLField(max_length=300)
    model = models.CharField(max_length=100)
    video_config = models.JSONField(default=dict, blank=True)
    encrypted_key = models.TextField()
    key_tail = models.CharField(max_length=4, blank=True)
    active = models.BooleanField(default=True)


class Asset(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=10)
    path = models.CharField(max_length=200)
    thumbnail = models.CharField(max_length=200, blank=True)
    sha256 = models.CharField(max_length=64)
    size = models.PositiveBigIntegerField()
    metadata = models.JSONField(default=dict)
    tags = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "sha256"], name="user_asset_hash")
        ]


class Script(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=160)
    synopsis = models.TextField(blank=True)
    style = models.CharField(max_length=20, default="甜宠")
    scenes = models.JSONField(default=list)
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)


class CanvasProject(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=160)
    schema_version = models.PositiveIntegerField(default=1)
    revision = models.PositiveIntegerField(default=1)
    document = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)


class Job(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    kind = models.CharField(max_length=20, default="compose")
    status = models.CharField(max_length=24, default="queued", db_index=True)
    stage = models.CharField(max_length=100, default="排队中")
    progress = models.PositiveIntegerField(default=0)
    remote_state = models.JSONField(default=dict, blank=True)
    snapshot = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    error_code = models.CharField(max_length=50, blank=True)
    idempotency_key = models.CharField(max_length=100)
    lease_owner = models.CharField(max_length=64, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "idempotency_key"], name="job_idempotency"
            )
        ]


class JobLog(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="logs")
    message = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)


class PromptTemplate(models.Model):
    name = models.CharField(max_length=30, unique=True)
    prompt = models.TextField()


class WorkerHeartbeat(models.Model):
    name = models.CharField(max_length=40, unique=True)
    updated_at = models.DateTimeField(auto_now=True)


class AIRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    provider = models.ForeignKey(Provider, on_delete=models.SET_NULL, null=True)
    service = models.CharField(max_length=10)
    endpoint = models.CharField(max_length=40)
    status = models.CharField(max_length=20, default="submitted")
    http_status = models.PositiveIntegerField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)
