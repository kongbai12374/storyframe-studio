import copy, json
from core.models import Provider, Job
from core.video_api import DEFAULT_CONFIG, provider_snapshot
from core.gateway import encrypt


def test_new_generation_uses_corrected_provider_but_preserves_history(context):
    user, _, client = context
    provider = Provider.objects.create(
        user=user,
        name="corrected",
        service="video",
        base_url="https://example.com",
        model="workflow",
        encrypted_key=encrypt("synthetic"),
        video_config=copy.deepcopy(DEFAULT_CONFIG),
    )
    original = {
        "video_provider": provider_snapshot(user, provider.id),
        "prompt": "test",
        "seconds": 5,
    }
    old = Job.objects.create(
        user=user,
        kind="video_api",
        status="failed",
        idempotency_key="old-config-task",
        snapshot=original,
        remote_state={"submission_state": "sending"},
    )
    provider.video_config = {
        **copy.deepcopy(DEFAULT_CONFIG),
        "submit_path": "/correct-workflow",
    }
    provider.save()
    response = client.post(
        f"/api/jobs/{old.id}/retry/",
        data=json.dumps(
            {
                "confirm_paid": True,
                "new_generation": True,
                "idempotency_key": "corrected-config-task",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 202
    new = Job.objects.get(pk=response.json()["id"])
    old.refresh_from_db()
    assert (
        new.snapshot["video_provider"]["config"]["submit_path"] == "/correct-workflow"
    )
    assert old.snapshot["video_provider"]["config"]["submit_path"] == "/videos"
