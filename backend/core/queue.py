import json, time, shutil, uuid
from pathlib import Path
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import Job, JobLog

ACTIVE = ["queued", "running", "cancel_requested"]


def resource_check():
    if shutil.disk_usage(settings.DATA_DIR).free < 5 * 1024**3:
        raise ValidationError("磁盘余量不足5GB，暂停接受新任务")
    path = settings.HOST_METRICS
    if not path:
        raise ValidationError("主机资源探针尚未配置，暂停接受新任务")
    try:
        d = json.loads(Path(path).read_text())
        if time.time() - d["timestamp"] > 30 or d["available_mb"] < 200:
            raise ValueError()
    except (OSError, ValueError, KeyError):
        raise ValidationError("主机内存余量不足或资源探针过期")
    for root in ["/sys/fs/cgroup"]:
        try:
            maximum = (Path(root) / "memory.max").read_text().strip()
            current = int((Path(root) / "memory.current").read_text())
            stats = dict(
                line.split()
                for line in (Path(root) / "memory.stat").read_text().splitlines()
            )
            reclaimable = int(stats.get("inactive_file", 0))
            if (
                maximum != "max"
                and int(maximum) - (current - reclaimable) < 64 * 1024 * 1024
            ):
                raise ValidationError("当前容器可用内存不足")
        except OSError:
            pass


def enqueue(user, kind, snapshot, key):
    if not isinstance(key, str) or not 8 <= len(key) <= 100:
        raise ValidationError("需要8至100位幂等键")
    if len(json.dumps(snapshot).encode()) > 550 * 1024:
        raise ValidationError("任务输入过大")
    with transaction.atomic():
        existing = Job.objects.filter(user=user, idempotency_key=key).first()
        if existing:
            return existing
        resource_check()
        if (
            Job.objects.filter(status__in=ACTIVE).count() >= 10
            or Job.objects.filter(user=user, status__in=ACTIVE).count() >= 2
        ):
            raise ValidationError("任务队列已满，请稍后再试")
        return Job.objects.create(
            user=user, kind=kind, snapshot=snapshot, idempotency_key=key
        )


def claim(owner):
    with transaction.atomic():
        if Job.objects.filter(status__in=["running", "cancel_requested"]).exists():
            return None
        job = Job.objects.filter(status="queued").order_by("id").first()
        if not job:
            return None
        n = Job.objects.filter(pk=job.pk, status="queued").update(
            status="running",
            stage="准备中",
            lease_owner=owner,
            heartbeat_at=timezone.now(),
            started_at=timezone.now(),
            attempts=job.attempts + 1,
        )
        if n:
            return Job.objects.get(pk=job.pk)


def update_job(job, **kwargs):
    kwargs["heartbeat_at"] = timezone.now()
    return Job.objects.filter(
        pk=job.pk, lease_owner=job.lease_owner, status="running"
    ).update(**kwargs)


def log(job, message):
    JobLog.objects.create(job=job, message=message[:500])
