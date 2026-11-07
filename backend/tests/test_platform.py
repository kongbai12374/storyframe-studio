import json, time, io
from unittest.mock import Mock, patch
import pytest
from django.test import Client
from rest_framework.exceptions import ValidationError
from core.models import Script, Asset, CanvasProject, Job, Profile, Provider
from core.validation import graph_validate, scenes_validate
from core.queue import enqueue, claim, update_job, resource_check
from core.gateway import encrypt, decrypt, public_target, GatewayError, request_provider
from core.views import canvas_snapshot


def test_decompression_bomb_is_validation_error(context, picture):
    from PIL import Image

    with patch(
        "core.storage.Image.open",
        side_effect=Image.DecompressionBombError("synthetic oversized image"),
    ):
        response = context[2].post("/api/assets/", {"file": picture})
        assert response.status_code == 400


def body(c, path, data, method="post"):
    return getattr(c, method)(
        path, data=json.dumps(data), content_type="application/json"
    )


def scene(**kw):
    return {
        "description": "树林中的一场相遇",
        "dialogue": "你好，世界。",
        "duration": 5,
        "image_id": None,
        "audio_id": None,
        **kw,
    }


def node(i, kind, entity=None):
    return {
        "id": i,
        "type": "studio",
        "position": {"x": 0, "y": 0},
        "data": {
            "kind": kind,
            "label": kind,
            **({"entity_id": entity} if entity else {}),
        },
    }


def document(nodes, edges=None):
    return {
        "nodes": nodes,
        "edges": edges or [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


def test_auth_and_csrf(context):
    a, b, c = context
    anonymous = Client(enforce_csrf_checks=True)
    assert anonymous.get("/api/scripts/").status_code == 403
    assert (
        body(
            anonymous,
            "/api/auth/login/",
            {"username": "alice", "password": "a-strong-test-password"},
        ).status_code
        == 403
    )
    token = anonymous.get("/api/csrf/").json()["csrfToken"]
    assert (
        anonymous.post(
            "/api/auth/login/",
            data=json.dumps(
                {"username": "alice", "password": "a-strong-test-password"}
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        ).status_code
        == 200
    )
    assert (
        anonymous.post(
            "/api/scripts/",
            data=json.dumps({"title": "x"}),
            content_type="application/json",
        ).status_code
        == 403
    )


def test_profile_password(context):
    a, b, c = context
    assert body(c, "/api/auth/me/", {"name": "创作者"}, "patch").status_code == 200
    assert (
        body(
            c,
            "/api/auth/me/",
            {"old_password": "wrong", "password": "another-long-password"},
            "patch",
        ).status_code
        == 400
    )
    assert (
        body(
            c,
            "/api/auth/me/",
            {
                "old_password": "a-strong-test-password",
                "password": "another-long-password",
            },
            "patch",
        ).status_code
        == 200
    )


def test_script_crud_conflict_export(context):
    a, b, c = context
    r = body(c, "/api/scripts/", {"title": "初稿", "scenes": [scene()]})
    assert r.status_code == 201
    ident = r.json()["id"]
    data = r.json()
    data["title"] = "修订稿"
    assert body(c, f"/api/scripts/{ident}/", data, "put").status_code == 200
    assert body(c, f"/api/scripts/{ident}/", data, "put").status_code == 409
    assert c.get(f"/api/scripts/{ident}/export/").status_code == 200
    assert body(c, f"/api/scripts/{ident}/duplicate/", {}).status_code == 201
    assert c.delete(f"/api/scripts/{ident}/").status_code == 204


@pytest.mark.parametrize(
    "scenes",
    [
        [],
        [scene(duration=0)],
        [scene(duration=61)],
        [scene(duration=float("nan"))],
        [scene(duration=True)],
        [scene(duration=40), scene(duration=40)],
    ],
)
def test_invalid_scenes(context, scenes):
    with pytest.raises(ValidationError):
        scenes_validate(scenes, context[0])


def test_upload_quota_and_private_file(context, picture):
    a, b, c = context
    r = c.post("/api/assets/", {"file": picture})
    assert r.status_code == 201
    ident = r.json()["id"]
    assert c.get(f"/api/assets/{ident}/file/").status_code == 200
    c.force_login(b)
    assert c.get(f"/api/assets/{ident}/file/").status_code == 404
    c.force_login(a)
    profile, _ = Profile.objects.get_or_create(user=a)
    profile.quota_bytes = 0
    profile.save()
    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "blue").save(buffer, "PNG")
    assert (
        c.post(
            "/api/assets/", {"file": SimpleUploadedFile("other.png", buffer.getvalue())}
        ).status_code
        == 400
    )


def test_upload_invalid_type(context):
    from django.core.files.uploadedfile import SimpleUploadedFile

    assert (
        context[2]
        .post("/api/assets/", {"file": SimpleUploadedFile("bad.svg", b"<svg></svg>")})
        .status_code
        == 400
    )


def test_ownership_for_resources(context):
    a, b, c = context
    s = Script.objects.create(user=b, title="private", scenes=[scene()])
    p = CanvasProject.objects.create(user=b, name="private", document=document([]))
    j = Job.objects.create(user=b, idempotency_key="private-key")
    for url in [
        f"/api/scripts/{s.id}/",
        f"/api/canvases/{p.id}/",
        f"/api/jobs/{j.id}/",
        f"/api/jobs/{j.id}/download/",
    ]:
        assert c.get(url).status_code == 404
    assert body(c, f"/api/jobs/{j.id}/cancel/", {}).status_code == 404


def test_encryption_and_redaction(context):
    a, b, c = context
    raw = "synthetic-api-key-1234"
    cipher = encrypt(raw)
    assert raw not in cipher and decrypt(cipher) == raw
    p = Provider.objects.create(
        user=a,
        name="test",
        service="llm",
        base_url="https://example.com/v1",
        model="test",
        encrypted_key=cipher,
        key_tail="1234",
    )
    data = c.get("/api/providers/").json()
    assert (
        raw not in json.dumps(data)
        and cipher not in json.dumps(data)
        and data[0]["key_hint"].endswith("1234")
    )
    c.force_login(b)
    assert c.delete(f"/api/providers/{p.id}/").status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://127.0.0.1",
        "https://169.254.169.254/latest/meta-data",
        "https://localhost",
        "https://user:pass@example.com",
        "https://example.com:8443",
        "https://[::1]",
    ],
)
def test_ssrf_rejected(url):
    with pytest.raises(GatewayError):
        public_target(url)


def test_dns_all_addresses_checked():
    with patch(
        "core.gateway.socket.getaddrinfo",
        return_value=[
            (2, 1, 6, "", ("8.8.8.8", 443)),
            (2, 1, 6, "", ("10.0.0.1", 443)),
        ],
    ):
        with pytest.raises(GatewayError):
            public_target("https://example.com")


def test_unknown_paid_request_not_retried(context):
    a, b, c = context
    p = Provider.objects.create(
        user=a,
        name="x",
        service="llm",
        base_url="https://example.com/v1",
        model="test",
        encrypted_key=encrypt("synthetic-key"),
    )
    with patch(
        "core.gateway.public_target",
        return_value=(
            __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(p.base_url),
            "8.8.8.8",
        ),
    ), patch("core.gateway.PinnedHTTPS") as conn:
        conn.return_value.request.side_effect = OSError("synthetic failure")
        with pytest.raises(GatewayError):
            request_provider(p, "chat/completions", {})
        assert conn.return_value.request.call_count == 1


def test_queue_idempotency_limits_lease(context):
    a, b, c = context
    one = enqueue(a, "compose", {}, "test-key-1")
    assert enqueue(a, "compose", {}, "test-key-1").id == one.id
    enqueue(a, "compose", {}, "test-key-2")
    with pytest.raises(ValidationError):
        enqueue(a, "compose", {}, "test-key-3")
    job = claim("owner-a")
    assert job.id == one.id
    assert claim("owner-b") is None
    job.lease_owner = "other"
    assert update_job(job, progress=90) == 0
    job.refresh_from_db()
    assert update_job(job, progress=10) == 1


def test_cancel_queued_running(context):
    a, b, c = context
    j = enqueue(a, "compose", {}, "cancel-key-1")
    assert body(c, f"/api/jobs/{j.id}/cancel/", {}).json()["status"] == "cancelled"
    j = enqueue(a, "compose", {}, "cancel-key-2")
    claim("owner")
    assert (
        body(c, f"/api/jobs/{j.id}/cancel/", {}).json()["status"] == "cancel_requested"
    )


def test_resource_stale_disk_full(context, settings, tmp_path):
    path = tmp_path / "metrics.json"
    settings.HOST_METRICS = str(path)
    path.write_text(json.dumps({"timestamp": time.time() - 60, "available_mb": 900}))
    with pytest.raises(ValidationError):
        resource_check()
    path.write_text(json.dumps({"timestamp": time.time(), "available_mb": 900}))
    with patch("core.queue.shutil.disk_usage", return_value=Mock(free=1024)):
        with pytest.raises(ValidationError):
            resource_check()


def test_canvas_conflict_reference_isolation(context):
    a, b, c = context
    foreign = Script.objects.create(user=b, title="private", scenes=[scene()])
    p = CanvasProject.objects.create(user=a, name="canvas", document=document([]))
    assert (
        body(
            c,
            f"/api/canvases/{p.id}/",
            {"revision": 1, "document": document([node("s", "script", foreign.id)])},
            "put",
        ).status_code
        == 400
    )
    payload = {"revision": 1, "document": document([node("note", "note")])}
    assert body(c, f"/api/canvases/{p.id}/", payload, "put").status_code == 200
    assert body(c, f"/api/canvases/{p.id}/", payload, "put").status_code == 409


def test_graph_rejects_duplicates_cycle_secrets(context):
    for doc in [
        document([node("x", "note"), node("x", "note")]),
        document(
            [node("a", "script"), node("b", "compose")],
            [
                {"id": "1", "source": "a", "target": "b"},
                {"id": "2", "source": "b", "target": "a"},
            ],
        ),
        document(
            [
                {
                    **node("x", "note"),
                    "data": {"kind": "note", "label": "x", "api_key": "secret"},
                }
            ]
        ),
    ]:
        with pytest.raises(ValidationError):
            graph_validate(doc, context[0])


def test_graph_100_nodes_limit(context):
    assert (
        len(
            graph_validate(
                document([node(str(i), "note") for i in range(100)]), context[0]
            )
        )
        == 100
    )
    with pytest.raises(ValidationError):
        graph_validate(document([node(str(i), "note") for i in range(101)]), context[0])


def test_snapshot_immutable(context):
    a, b, c = context
    s = Script.objects.create(user=a, title="snapshot", scenes=[scene()])
    p = CanvasProject.objects.create(
        user=a,
        name="c",
        document=document(
            [node("s", "script", s.id), node("c", "compose")],
            [{"id": "edge", "source": "s", "target": "c"}],
        ),
    )
    snap = canvas_snapshot(p, a)
    s.scenes = [scene(duration=9)]
    s.save()
    assert snap["entities"]["s"]["scenes"][0]["duration"] == 5


def test_cancel_process_group(context, tmp_path):
    from core.video import run_process, Cancelled

    j = Job.objects.create(
        user=context[0],
        idempotency_key="process-cancel",
        status="cancel_requested",
        lease_owner="owner",
    )
    j._start = time.monotonic()
    fake = Mock()
    fake.poll.return_value = None
    fake.pid = 1234
    with patch("core.video.subprocess.Popen", return_value=fake), patch(
        "core.video.os.killpg"
    ) as kill:
        with pytest.raises(Cancelled):
            run_process(j, ["dummy"], tmp_path)
        kill.assert_called_once()
        assert fake.wait.called


def test_retry_requires_paid_confirmation(context):
    a, b, c = context
    j = Job.objects.create(
        user=a,
        kind="llm",
        status="failed",
        idempotency_key="paid-test",
        snapshot={"synopsis": "x", "style": "甜宠"},
    )
    assert (
        body(
            c, f"/api/jobs/{j.id}/retry/", {"idempotency_key": "retry-test"}
        ).status_code
        == 400
    )
    assert (
        body(
            c,
            f"/api/jobs/{j.id}/retry/",
            {"idempotency_key": "retry-test", "confirm_paid": True},
        ).status_code
        == 202
    )


def test_invalid_json_body_rejected(context):
    assert (
        context[2]
        .post("/api/scripts/", data="[]", content_type="application/json")
        .status_code
        == 400
    )
    assert (
        context[2]
        .post("/api/scripts/", data="{", content_type="application/json")
        .status_code
        == 400
    )


def test_paid_tts_retry_requires_confirmation(context):
    a, b, c = context
    j = Job.objects.create(
        user=a,
        kind="compose",
        status="failed",
        idempotency_key="tts-paid-test",
        snapshot={"use_tts": True},
    )
    assert (
        body(
            c, f"/api/jobs/{j.id}/retry/", {"idempotency_key": "tts-retry-key"}
        ).status_code
        == 400
    )


def test_llm_adapter_fixture_without_real_api(context):
    from core.gateway import llm

    a = context[0]
    Provider.objects.create(
        user=a,
        name="fixture",
        service="llm",
        base_url="https://example.com/v1",
        model="fixture",
        encrypted_key=encrypt("synthetic"),
    )
    expected = {"title": "测试剧本", "scenes": [scene()]}
    with patch(
        "core.gateway.request_provider",
        return_value=json.dumps(
            {"choices": [{"message": {"content": json.dumps(expected)}}]}
        ).encode(),
    ):
        assert llm(a, "测试梗概", "甜宠") == expected
