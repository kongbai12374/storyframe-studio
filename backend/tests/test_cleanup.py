import os, time
from core.models import Job
from core.cleanup import cleanup_stale


def test_cleanup_keeps_active_and_fresh_directories(context, settings):
    user = context[0]
    active = Job.objects.create(
        user=user, idempotency_key="cleanup-active", status="running"
    )
    failed = Job.objects.create(
        user=user, idempotency_key="cleanup-failed", status="failed"
    )
    root = settings.MEDIA_ROOT / "tmp"
    root.mkdir()
    for ident in [str(active.id), str(failed.id), "9999"]:
        folder = root / ident
        folder.mkdir()
        (folder / "fixture.txt").write_text("test")
        if ident != "9999":
            os.utime(folder, (time.time() - 90000, time.time() - 90000))
    assert cleanup_stale() == 1
    assert (root / str(active.id)).exists() and (root / "9999").exists()
    assert not (root / str(failed.id)).exists()
