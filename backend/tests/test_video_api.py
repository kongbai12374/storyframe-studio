import copy, json, time
from urllib.parse import urlsplit
from unittest.mock import Mock, patch
import pytest
from rest_framework.exceptions import ValidationError
from core.models import Provider, Job, Profile, AIRequest
from core.video_api import (
    DEFAULT_CONFIG,
    validate_config,
    extract,
    render,
    prepare_snapshot,
    generate,
    transport,
    download,
)
from core.gateway import encrypt, GatewayError
from core.video import Cancelled


@pytest.fixture
def video(context):
    user = context[0]
    provider = Provider.objects.create(
        user=user,
        name="User-selected provider",
        service="video",
        base_url="https://api.example.com/v1",
        model="user-video-model",
        encrypted_key=encrypt("synthetic-key"),
        key_tail="-key",
        video_config=copy.deepcopy(DEFAULT_CONFIG),
    )
    snapshot = prepare_snapshot(
        user,
        {
            "provider_id": provider.id,
            "prompt": "A quiet forest at sunrise",
            "seconds": 5,
        },
    )
    job = Job.objects.create(
        user=user,
        kind="video_api",
        status="running",
        lease_owner="worker-fixture",
        snapshot=snapshot,
        idempotency_key="video-fixture-key",
    )
    job._start = time.monotonic()
    return provider, snapshot, job


def test_nested_mapping_and_types():
    assert (
        extract({"data": [{"url": "https://example.com/video"}]}, "data.0.url")
        == "https://example.com/video"
    )
    assert extract({}, "data.nope") is None
    assert render(
        {"duration": "{{seconds}}", "text": "Prompt: {{prompt}}"},
        {"seconds": 8, "prompt": "hello"},
    ) == {"duration": 8, "text": "Prompt: hello"}


@pytest.mark.parametrize(
    "changes",
    [
        {"submit_path": "https://evil.example/videos"},
        {"poll_path": "//evil.example/x"},
        {"auth_header": "Host"},
        {"auth_prefix": "Bearer\r\nInjected: yes"},
        {"request_body": {"api_key": "not-allowed"}},
        {"poll_seconds": 0},
        {"success_values": ["completed"], "failure_values": ["completed"]},
        {"status_field": "data.__class__()"},
        {"request_body": {"prompt": "{{unknown}}"}},
    ],
)
def test_bad_protocol_config(changes):
    with pytest.raises(ValidationError):
        validate_config(changes)


def test_async_submit_once_then_poll(video):
    provider, snapshot, job = video
    with (
        patch(
            "core.video_api.transport",
            side_effect=[
                {"id": "provider-task-1", "status": "queued"},
                {"id": "provider-task-1", "status": "processing", "progress": 55},
                {
                    "id": "provider-task-1",
                    "status": "completed",
                    "video_url": "https://cdn.example/video.mp4",
                },
            ],
        ) as request,
        patch(
            "core.video_api.download",
            return_value={"path": "outputs/fixture.mp4", "size": 3, "duration": 5},
        ),
        patch("core.video_api.time.sleep"),
    ):
        result = generate(job, snapshot)
    assert result["duration"] == 5
    assert request.call_count == 3
    assert request.call_args_list[0].args[4] == "POST"
    assert all(len(c.args) == 4 for c in request.call_args_list[1:])
    job.refresh_from_db()
    assert (
        job.remote_state["task_id"] == "provider-task-1"
        and job.remote_state["status"] == "completed"
    )


def test_resume_only_queries_original_id(video):
    provider, snapshot, job = video
    job.remote_state = {
        "provider_id": provider.id,
        "task_id": "old-task",
        "submission_state": "accepted",
        "status": "processing",
    }
    job.save()
    with (
        patch(
            "core.video_api.transport",
            return_value={
                "status": "completed",
                "video_url": "https://cdn.example/video.mp4",
            },
        ) as request,
        patch("core.video_api.download", return_value={"path": "outputs/existing.mp4"}),
    ):
        generate(job, snapshot)
    assert request.call_count == 1 and request.call_args.args[3].endswith("/old-task")


def test_unknown_submit_never_reposts(video):
    provider, snapshot, job = video
    job.remote_state = {"submission_state": "sending"}
    job.save()
    with patch("core.video_api.transport") as request:
        with pytest.raises(GatewayError, match="不会重复"):
            generate(job, snapshot)
    request.assert_not_called()


def test_sync_result(video):
    provider, snapshot, job = video
    snapshot["video_provider"]["config"]["mode"] = "sync"
    with (
        patch(
            "core.video_api.transport",
            return_value={"video_url": "https://cdn.example/result.mp4"},
        ) as request,
        patch("core.video_api.download", return_value={"path": "outputs/sync.mp4"}),
    ):
        generate(job, snapshot)
    assert request.call_count == 1


def test_cancel_records_supplier_uncertainty(video):
    provider, snapshot, job = video
    with (
        patch("core.video_api.check", side_effect=[None, Cancelled()]),
        patch(
            "core.video_api.transport",
            return_value={"id": "remote-cancel", "status": "queued"},
        ),
    ):
        with pytest.raises(Cancelled):
            generate(job, snapshot)
    job.refresh_from_db()
    assert job.remote_state["task_id"] == "remote-cancel"
    assert job.remote_state["cancellation"] == "local_cancel_only_provider_may_continue"


def test_submit_charge_and_202_response(video):
    provider, snapshot, job = video
    connection = Mock()
    response = Mock(status=202)
    response.read.side_effect = [b'{"id":"task"}', b""]
    connection.getresponse.return_value = response
    with (
        patch(
            "core.video_api.public_target",
            return_value=(urlsplit(provider.base_url), "8.8.8.8"),
        ),
        patch("core.video_api.PinnedHTTPS", return_value=connection),
    ):
        assert (
            transport(
                job,
                provider,
                snapshot["video_provider"],
                "/videos",
                "POST",
                {"prompt": "test"},
                charge=True,
            )["id"]
            == "task"
        )
    assert Profile.objects.get(user=job.user).api_calls_remaining == 99
    assert AIRequest.objects.get(user=job.user).status == "succeeded"


def test_poll_does_not_charge_generation_quota(video):
    provider, snapshot, job = video
    Profile.objects.create(user=job.user, api_calls_remaining=8)
    response = Mock(status=200)
    response.read.side_effect = [b'{"status":"processing"}', b""]
    connection = Mock()
    connection.getresponse.return_value = response
    with (
        patch(
            "core.video_api.public_target",
            return_value=(urlsplit(provider.base_url), "8.8.8.8"),
        ),
        patch("core.video_api.PinnedHTTPS", return_value=connection),
    ):
        transport(job, provider, snapshot["video_provider"], "/videos/task")
    assert (
        Profile.objects.get(user=job.user).api_calls_remaining == 8
        and AIRequest.objects.count() == 0
    )


def test_download_does_not_leak_auth_to_cdn(video):
    provider, snapshot, job = video
    response = Mock(status=200)
    response.read.side_effect = [b"fixture-media", b""]
    connection = Mock()
    connection.getresponse.return_value = response
    info = {
        "streams": [{"codec_type": "video", "width": 1280, "height": 720}],
        "format": {"duration": "5", "format_name": "mov,mp4"},
    }
    with (
        patch(
            "core.video_api.public_target",
            return_value=(urlsplit("https://cdn.example/video.mp4"), "8.8.8.8"),
        ),
        patch("core.video_api.PinnedHTTPS", return_value=connection),
        patch("core.video_api.probe", return_value=info),
    ):
        result = download(
            job,
            provider,
            snapshot["video_provider"],
            "https://cdn.example/video.mp4?signature=synthetic",
        )
    assert result["size"] == 13 and connection.request.call_args.kwargs["headers"] == {}
    assert "signature=synthetic" in connection.request.call_args.args[1]


def test_provider_and_reference_ownership(context):
    a, b, c = context
    provider = Provider.objects.create(
        user=b,
        name="private",
        service="video",
        base_url="https://example.com",
        model="x",
        encrypted_key=encrypt("fixture"),
    )
    with pytest.raises(ValidationError):
        prepare_snapshot(a, {"provider_id": provider.id, "prompt": "x"})


def test_video_endpoint_requires_cost_confirmation(video, context):
    provider, snapshot, job = video
    c = context[2]
    r = c.post(
        "/api/jobs/",
        data=json.dumps(
            {
                "kind": "video_api",
                "provider_id": provider.id,
                "prompt": "test",
                "idempotency_key": "new-video-request",
            }
        ),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_retry_carries_remote_id_instead_of_resubmit(video, context):
    provider, snapshot, job = video
    job.status = "interrupted"
    job.remote_state = {
        "task_id": "original-id",
        "submission_state": "accepted",
        "provider_id": provider.id,
    }
    job.save()
    r = context[2].post(
        f"/api/jobs/{job.id}/retry/",
        data=json.dumps(
            {"confirm_paid": True, "idempotency_key": "resume-video-request"}
        ),
        content_type="application/json",
    )
    assert r.status_code == 202
    created = Job.objects.get(pk=r.json()["id"])
    assert created.snapshot["resume_remote_state"]["task_id"] == "original-id"


def test_complete_adapter_downloads_real_mp4_fixture(video, context):
    import io
    from pathlib import Path

    provider, snapshot, job = video
    fixture = Path(__file__).resolve().parents[2] / "docs/samples/sample-15s.mp4"
    payload = fixture.read_bytes()
    calls = []

    class Reply:
        def __init__(self, data, status=200):
            self.status = status
            self.stream = io.BytesIO(data)

        def read(self, size):
            return self.stream.read(size)

    class Connection:
        def __init__(self, *args):
            self.host = args[0]

        def request(self, method, path, **kwargs):
            self.method = method
            self.path = path
            calls.append((method, self.host, path))

        def getresponse(self):
            if self.method == "POST":
                return Reply(b'{"id":"fixture-remote-id","status":"queued"}', 202)
            if self.host == "cdn.example":
                return Reply(payload)
            return Reply(
                b'{"status":"completed","video_url":"https://cdn.example/sample.mp4?signature=fixture"}'
            )

        def close(self):
            pass

    with (
        patch(
            "core.video_api.public_target",
            side_effect=lambda url: (urlsplit(url), "8.8.8.8"),
        ),
        patch("core.video_api.PinnedHTTPS", Connection),
        patch("core.video_api.time.sleep"),
    ):
        result = generate(job, snapshot)
    assert result["duration"] >= 14 and result["size"] == len(payload)
    job.result = result
    job.status = "succeeded"
    job.save()
    response = context[2].get(f"/api/jobs/{job.id}/download/")
    assert (
        response.status_code == 200 and b"".join(response.streaming_content) == payload
    )
    assert sum(method == "POST" for method, host, path in calls) == 1
