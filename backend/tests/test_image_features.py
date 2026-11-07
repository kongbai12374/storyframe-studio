import base64
import copy
import io
import time
from unittest.mock import patch, Mock
import pytest
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError
from core.models import Asset, Provider, Job, CanvasProject, Script
from core.gateway import encrypt, GatewayError
from core.storage import save_upload, safe_path
from core.video_api import (
    DEFAULT_CONFIG,
    generate,
    prepare_image_snapshot,
    prepare_snapshot,
    render,
    validate_images,
)
from core.image_api import save_result, decode_image, fetch_image


def upload(user, color):
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buf, "PNG")
    return save_upload(user, SimpleUploadedFile("image.png", buf.getvalue()))


@pytest.fixture
def image_job(context):
    user = context[0]
    config = {
        **copy.deepcopy(DEFAULT_CONFIG),
        "mode": "sync",
        "submit_path": "/images/generations",
        "poll_path": "",
        "request_body": {
            "model": "{{model}}",
            "prompt": "{{prompt}}",
            "size": "{{size}}",
            "n": "{{count}}",
        },
        "video_url_field": "data",
        "output_format": "base64",
    }
    provider = Provider.objects.create(
        user=user,
        name="Image fixture",
        service="image",
        base_url="https://images.example.com/v1",
        model="user-image-model",
        video_config=config,
        encrypted_key=encrypt("synthetic-key"),
    )
    snapshot = prepare_image_snapshot(
        user, {"provider_id": provider.id, "prompt": "forest", "count": 2}
    )
    job = Job.objects.create(
        user=user,
        kind="image_api",
        status="running",
        lease_owner="fixture",
        snapshot=snapshot,
        idempotency_key="image-fixture",
    )
    job._start = time.monotonic()
    return provider, snapshot, job


def png(color):
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_image_sync_generates_private_assets(image_job, context):
    provider, snapshot, job = image_job
    with patch(
        "core.video_api.transport",
        return_value={"data": [{"b64_json": png("red")}, {"b64_json": png("blue")}]},
    ) as request:
        result = generate(job, snapshot)
    assert request.call_count == 1
    assert request.call_args.args[5]["n"] == 2
    assert result["source"] == "image_api" and len(result["asset_ids"]) == 2
    assert Asset.objects.filter(user=job.user, kind="image").count() == 2
    assert (
        "path" not in result and "size" not in result
    )  # Assets account for image storage exactly once.
    for asset in Asset.objects.all():
        assert safe_path(asset.path).exists()
        assert context[2].get(f"/api/assets/{asset.id}/file/").status_code == 200
    job.refresh_from_db()
    assert job.remote_state["status"] == "completed"


def test_image_async_resume_does_not_repost(image_job):
    provider, snapshot, job = image_job
    snapshot["video_provider"]["config"].update(
        mode="async", poll_path="/tasks/{{task_id}}"
    )
    job.remote_state = {"task_id": "original", "submission_state": "accepted"}
    job.save()
    with patch(
        "core.video_api.transport",
        return_value={"status": "completed", "data": [{"b64_json": png("red")}]},
    ) as request:
        generate(job, snapshot)
    assert request.call_count == 1 and request.call_args.args[3] == "/tasks/original"
    assert len(request.call_args.args) == 4


def test_image_unknown_submission_does_not_repost(image_job):
    provider, snapshot, job = image_job
    job.remote_state = {"submission_state": "sending"}
    job.save()
    with (
        patch("core.video_api.transport") as request,
        pytest.raises(GatewayError, match="不会重复"),
    ):
        generate(job, snapshot)
    request.assert_not_called()


def test_image_invalid_output_cannot_create_audio(image_job):
    provider, snapshot, job = image_job
    with pytest.raises(GatewayError):
        save_result(job, provider, snapshot["video_provider"], "bm90LWltYWdl")
    assert Asset.objects.count() == 0
    with pytest.raises(GatewayError):
        decode_image("not valid!!")


def test_image_url_auth_never_leaks_to_cdn(image_job):
    provider, snapshot, job = image_job
    conn = Mock()
    response = Mock(status=200)
    response.read.side_effect = [base64.b64decode(png("green")), b""]
    conn.getresponse.return_value = response
    from urllib.parse import urlsplit

    with (
        patch(
            "core.image_api.public_target",
            return_value=(
                urlsplit("https://cdn.example.com/image.png"),
                "93.184.216.34",
            ),
        ),
        patch("core.image_api.PinnedHTTPS", return_value=conn),
    ):
        assert fetch_image(
            job,
            provider,
            snapshot["video_provider"],
            "https://cdn.example.com/image.png?signature=fixture",
        )
    assert conn.request.call_args.kwargs["headers"] == {}
    assert "signature=fixture" in conn.request.call_args.args[1]


def test_multiple_images_order_and_ownership(context):
    user, other, client = context
    a, b = upload(user, "red"), upload(user, "blue")
    foreign = upload(other, "green")
    assert validate_images(user, {"image_ids": [b.id, a.id]}) == [b.id, a.id]
    assert validate_images(user, {"image_id": a.id}) == [a.id]
    assert render(
        {"images": "{{images_data_urls}}"}, {"images_data_urls": ["a", "b"]}
    ) == {"images": ["a", "b"]}
    for ids in [[foreign.id], [a.id, a.id], [True], list(range(1, 11))]:
        with pytest.raises(ValidationError):
            validate_images(user, {"image_ids": ids})


def test_video_submits_all_images_in_order(context):
    user = context[0]
    a, b = upload(user, "red"), upload(user, "blue")
    provider = Provider.objects.create(
        user=user,
        name="multi",
        service="video",
        base_url="https://example.com",
        model="multi",
        video_config={
            **DEFAULT_CONFIG,
            "mode": "sync",
            "request_body": {
                "images": "{{images_data_urls}}",
                "first": "{{image_data_url}}",
            },
        },
        encrypted_key=encrypt("fixture"),
    )
    snapshot = prepare_snapshot(
        user, {"provider_id": provider.id, "prompt": "test", "image_ids": [b.id, a.id]}
    )
    job = Job.objects.create(
        user=user,
        kind="video_api",
        status="running",
        lease_owner="fixture",
        snapshot=snapshot,
        idempotency_key="multi",
    )
    job._start = time.monotonic()
    with (
        patch(
            "core.video_api.transport",
            return_value={"video_url": "https://example.com/video.mp4"},
        ) as request,
        patch("core.video_api.download", return_value={"path": "fixture"}),
    ):
        generate(job, snapshot)
    body = request.call_args.args[5]
    assert len(body["images"]) == 2 and body["first"] == body["images"][0]
    assert (
        base64.b64decode(body["images"][0].split(",")[1])
        == safe_path(b.path).read_bytes()
    )


def test_image_submit_requires_fee_confirmation_and_owned_provider(image_job, context):
    provider, _, job = image_job
    client = context[2]
    data = {
        "kind": "image_api",
        "provider_id": provider.id,
        "prompt": "forest",
        "idempotency_key": "new",
    }
    assert (
        client.post("/api/jobs/", data, content_type="application/json").status_code
        == 400
    )
    provider.user = context[1]
    provider.save()
    data["confirm_paid"] = True
    assert (
        client.post("/api/jobs/", data, content_type="application/json").status_code
        == 400
    )


def test_image_new_generation_uses_current_config(image_job, context):
    provider, snapshot, job = image_job
    job.status = "failed"
    job.remote_state = {"submission_state": "sending"}
    job.save()
    provider.video_config["submit_path"] = "/new-image-path"
    provider.save()
    response = context[2].post(
        f"/api/jobs/{job.id}/retry/",
        {
            "confirm_paid": True,
            "new_generation": True,
            "idempotency_key": "retry-image",
        },
        content_type="application/json",
    )
    assert response.status_code == 202
    new = Job.objects.get(pk=response.json()["id"])
    assert new.snapshot["video_provider"]["config"]["submit_path"] == "/new-image-path"
    assert new.snapshot["video_provider"]["service"] == "image"


def test_job_delete_rejects_active_and_other_users(context):
    user, other, client = context
    job = Job.objects.create(
        user=user, kind="compose", snapshot={}, idempotency_key="active"
    )
    assert client.delete(f"/api/jobs/{job.id}/").status_code == 409
    job.status = "failed"
    job.user = other
    job.save()
    assert client.delete(f"/api/jobs/{job.id}/").status_code == 404
    assert Job.objects.filter(pk=job.id).exists()


def test_job_delete_cleans_video_but_keeps_generated_assets(
    context, django_capture_on_commit_callbacks
):
    user, _, client = context
    asset = upload(user, "purple")
    safe_path("outputs").mkdir()
    path = safe_path("outputs/test.mp4")
    path.write_bytes(b"fixture")
    job = Job.objects.create(
        user=user,
        status="succeeded",
        snapshot={},
        result={"path": "outputs/test.mp4", "asset_ids": [asset.id]},
        idempotency_key="finished",
    )
    with django_capture_on_commit_callbacks(execute=True):
        assert client.delete(f"/api/jobs/{job.id}/").status_code == 204
    assert not path.exists() and Asset.objects.filter(pk=asset.id).exists()


def test_job_delete_protects_canvas_result(context):
    user, _, client = context
    job = Job.objects.create(
        user=user, status="failed", snapshot={}, idempotency_key="referenced"
    )
    CanvasProject.objects.create(
        user=user,
        name="fixture",
        document={"nodes": [{"data": {"kind": "result", "entity_id": job.id}}]},
    )
    assert client.delete(f"/api/jobs/{job.id}/").status_code == 409


def test_asset_delete_protects_multiimage_jobs(context):
    user, _, client = context
    asset = upload(user, "yellow")
    Job.objects.create(
        user=user, snapshot={"image_ids": [asset.id]}, idempotency_key="multi-active"
    )
    assert client.delete(f"/api/assets/{asset.id}/").status_code == 409


def test_image_api_audit_and_quota_use_image_service(image_job):
    from urllib.parse import urlsplit
    from core.video_api import transport
    from core.models import Profile, AIRequest
    import json

    provider, snapshot, job = image_job
    conn = Mock()
    response = Mock(status=200)
    response.read.side_effect = [json.dumps({"data": []}).encode(), b""]
    conn.getresponse.return_value = response
    with (
        patch(
            "core.video_api.public_target",
            return_value=(urlsplit(provider.base_url), "93.184.216.34"),
        ),
        patch("core.video_api.PinnedHTTPS", return_value=conn),
    ):
        transport(
            job,
            provider,
            snapshot["video_provider"],
            "/images/generations",
            "POST",
            {},
            charge=True,
        )
    assert Profile.objects.get(user=job.user).api_calls_remaining == 99
    assert AIRequest.objects.get().service == "image"
    assert AIRequest.objects.get().endpoint == "image.submit"


def test_image_quota_failure_leaves_no_files(image_job):
    from core.models import Profile

    provider, snapshot, job = image_job
    Profile.objects.create(user=job.user, quota_bytes=1)
    with pytest.raises(ValidationError):
        save_result(job, provider, snapshot["video_provider"], png("red"))
    assert Asset.objects.count() == 0
    from django.conf import settings

    assert not [p for p in settings.MEDIA_ROOT.rglob("*") if p.is_file()]


def test_script_delete_protects_canvas_reference(context):
    user, _, client = context
    script = Script.objects.create(user=user, title="fixture", scenes=[])
    canvas = CanvasProject.objects.create(
        user=user,
        name="fixture",
        document={"nodes": [{"data": {"kind": "script", "entity_id": script.id}}]},
    )
    assert client.delete(f"/api/scripts/{script.id}/").status_code == 409
    canvas.delete()
    assert client.delete(f"/api/scripts/{script.id}/").status_code == 204
