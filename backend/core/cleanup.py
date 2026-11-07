"""Remove only inactive job-owned temporary directories older than 24 hours."""

import shutil
import time
from django.conf import settings
from .models import Job


def cleanup_stale(now=None):
    root = settings.MEDIA_ROOT / "tmp"
    if not root.exists():
        return 0
    cutoff = (now or time.time()) - 86400
    active = set(
        str(x)
        for x in Job.objects.filter(
            status__in=["queued", "running", "cancel_requested"]
        ).values_list("id", flat=True)
    )
    removed = 0
    for folder in root.iterdir():
        if (
            folder.is_symlink()
            or not folder.is_dir()
            or not folder.name.isdigit()
            or folder.name in active
        ):
            continue
        if folder.stat().st_mtime < cutoff:
            shutil.rmtree(folder)
            removed += 1
    return removed
