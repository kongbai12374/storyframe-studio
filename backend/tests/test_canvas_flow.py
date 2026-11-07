import copy, io, time, wave
from unittest.mock import patch
from decimal import Decimal
import pytest
from django.test import Client
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from rest_framework.exceptions import ValidationError
from core.models import Job, Provider, Profile, CanvasProject, Asset
from core.gateway import GatewayError, encrypt
from core.storage import save_upload, safe_path, used_bytes
from core.video_api import DEFAULT_CONFIG, persist, node_state
from core.canvas_flow import validate_budget, run_flow, voiceover
from core.asset_links import asset_link
from core.validation import graph_validate


def node(ident, kind, **data):
    return {
        "id": ident,
        "type": "studio",
        "position": {"x": 0, "y": 0},
        "data": {"kind": kind, "label": ident, **data},
    }


def edge(a, b):
    return {"id": a + "-" + b, "source": a, "target": b}


@pytest.fixture
def running(context):
    job = Job.objects.create(
        user=context[0],
        kind="canvas",
        status="running",
        lease_owner="flow-test",
        snapshot={},
        idempotency_key="flow-test",
    )
    job._start = time.monotonic()
    return job


def test_scoped_task_ids_do_not_cross_nodes(running):
    running.remote_state = {"flow": True, "node_states": {}, "completed": {}}
    running._node_key = "image1"
    persist(running, {"task_id": "image-task"})
    running._node_key = "video"
    assert node_state(running) == {}
    persist(running, {"task_id": "video-task"})
    running._node_key = "image1"
    assert node_state(running)["task_id"] == "image-task"
    running.refresh_from_db()
    assert running.remote_state["node_states"]["video"]["task_id"] == "video-task"


def test_conservative_budget_refuses_overspend_before_submission():
    snapshot = {
        "document": {
            "nodes": [
                node("image", "image_api"),
                node("video", "video_api", seconds=10),
            ]
        },
        "order": ["image", "video"],
        "video_providers": {
            "image": {
                "model": "doubao-seedream-5-0-flash",
                "base_url": "https://www.autodl.art/api/v1",
            },
            "video": {
                "model": "minimax_h3_lightx2v_v5_15s",
                "base_url": "https://www.autodl.art",
            },
        },
    }
    with pytest.raises(ValidationError):
        validate_budget(snapshot, "0.50")
    assert Decimal(validate_budget(snapshot, "3")["estimated_yuan"]) == Decimal("0.85")
    snapshot["video_providers"]["video"]["model"] = "unpriced"
    with pytest.raises(ValidationError):
        validate_budget(snapshot, "3")


def test_private_links_need_signature_and_expire(context, picture):
    asset = save_upload(context[0], picture)
    url = asset_link(context[0], asset.id)
    path = url.split("https://studio.example.com")[-1]
    anon = Client()
    assert anon.get(path).status_code == 200
    assert anon.get(path[:-2] + "x/").status_code == 404
    with patch("django.core.signing.time.time", return_value=time.time() + 3601):
        assert anon.get(path).status_code == 404
    assert anon.get(f"/api/assets/{asset.id}/file/").status_code in [401, 403]


def test_flow_sends_two_generated_images_and_tts_to_video_and_mux(
    running, context, picture
):
    asset = save_upload(context[0], picture)
    doc = {
        "nodes": [
            node("llm", "llm", text="adult woman two shots"),
            node("i1", "image_api", scene_index=1),
            node("i2", "image_api", scene_index=2),
            node("tts", "tts", entity_id=asset.id),
            node("video", "video_api", seconds=10),
            node("mux", "voiceover", seconds=10),
            node("result", "result"),
        ],
        "edges": [
            edge("llm", "i1"),
            edge("llm", "i2"),
            edge("llm", "tts"),
            edge("llm", "video"),
            edge("i1", "video"),
            edge("i2", "video"),
            edge("tts", "mux"),
            edge("video", "mux"),
            edge("mux", "result"),
        ],
    }
    snap = {
        "document": doc,
        "order": ["llm", "i1", "i2", "tts", "video", "mux", "result"],
        "entities": {},
        "video_providers": {
            k: {"service": v}
            for k, v in [
                ("i1", "image"),
                ("i2", "image"),
                ("tts", "tts"),
                ("video", "video"),
            ]
        },
        "budget": {
            "limit_yuan": "3",
            "plan": {"llm": ".1", "i1": ".15", "i2": ".15", "tts": ".1", "video": ".7"},
        },
    }
    running.snapshot = snap
    running.save()
    generated = []

    def generate(job, request):
        generated.append((job._node_key, request))
        if job._node_key in ["i1", "i2"]:
            return {"asset_ids": [asset.id]}
        if job._node_key == "tts":
            return {"audio_id": asset.id, "asset_id": asset.id}
        return {"path": "outputs/raw.mp4", "size": 10, "duration": 10}

    script = {
        "script_id": 1,
        "scenes": [
            {"description": "first shot", "dialogue": "hello"},
            {"description": "second shot", "dialogue": "world"},
        ],
    }
    with (
        patch("core.management.commands.worker.make_script", return_value=script),
        patch("core.canvas_flow.generate", side_effect=generate),
        patch(
            "core.canvas_flow.voiceover",
            return_value={"path": "outputs/final.mp4", "size": 20, "duration": 10},
        ),
    ):
        result = run_flow(running)
    assert [x[0] for x in generated] == ["i1", "i2", "tts", "video"]
    assert "first shot" in generated[0][1]["prompt"]
    assert "second shot" in generated[1][1]["prompt"]
    assert generated[2][1]["prompt"] == "helloworld"
    assert generated[3][1]["image_ids"] == [
        asset.id
    ]  # Dedup identical fixture assets; real nodes return distinct images.
    assert result["duration"] == 10 and result["budget"]["reserved_yuan"] == "1.20"
    assert len(running.remote_state["completed"]) == 7


def test_resume_skips_completed_paid_nodes(running, context, picture):
    asset = save_upload(context[0], picture)
    running.snapshot = {
        "document": {
            "nodes": [node("i", "image_api"), node("r", "result")],
            "edges": [edge("i", "r")],
        },
        "order": ["i", "r"],
        "entities": {},
        "resume_remote_state": {
            "flow": True,
            "node_states": {"i": {"status": "completed"}},
            "completed": {"i": {"asset_ids": [asset.id]}},
            "reservations": {"i": ".15"},
        },
    }
    running.save()
    with patch("core.canvas_flow.generate") as generate:
        result = run_flow(running)
    generate.assert_not_called()
    assert result["asset_ids"] == [asset.id]


def test_unknown_llm_never_reposts(running):
    running.snapshot = {
        "document": {"nodes": [node("llm", "llm")], "edges": []},
        "order": ["llm"],
        "budget": {"plan": {"llm": ".1"}, "limit_yuan": "3"},
    }
    running.remote_state = {
        "flow": True,
        "node_states": {"llm": {"submission_state": "sending"}},
        "completed": {},
        "reservations": {"llm": ".1"},
    }
    running.save()
    with (
        patch("core.management.commands.worker.make_script") as script,
        pytest.raises(GatewayError, match="重复收费"),
    ):
        run_flow(running)
    script.assert_not_called()


def test_checkpoints_count_intermediate_storage_once_and_delete(
    context, django_capture_on_commit_callbacks
):
    user, _, client = context
    safe_path("outputs").mkdir()
    safe_path("outputs/raw.mp4").write_bytes(b"raw")
    safe_path("outputs/final.mp4").write_bytes(b"final")
    job = Job.objects.create(
        user=user,
        status="succeeded",
        snapshot={},
        remote_state={
            "completed": {
                "video": {"path": "outputs/raw.mp4", "size": 3},
                "mux": {"path": "outputs/final.mp4", "size": 5},
            }
        },
        result={"path": "outputs/final.mp4", "size": 5},
        idempotency_key="storage",
    )
    assert used_bytes(user) == 8
    with django_capture_on_commit_callbacks(execute=True):
        assert client.delete(f"/api/jobs/{job.id}/").status_code == 204
    assert (
        not safe_path("outputs/raw.mp4").exists()
        and not safe_path("outputs/final.mp4").exists()
    )


def test_real_local_voiceover_preserves_audio_and_duration(running, context):
    import subprocess

    safe_path("outputs").mkdir()
    raw = safe_path("outputs/raw.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=160x90:r=24",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            str(raw),
        ],
        check=True,
    )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 8000)
    audio = save_upload(context[0], SimpleUploadedFile("voice.wav", buf.getvalue()))
    result = voiceover(
        running,
        [
            {"path": "outputs/raw.mp4", "size": raw.stat().st_size},
            {"audio_id": audio.id},
        ],
        1,
    )
    from core.storage import probe

    info = probe(safe_path(result["path"]))
    assert result["duration"] == 1
    assert {s["codec_type"] for s in info["streams"]} == {"audio", "video"}


def test_explicit_llm_auth_rejection_is_recoverable(running):
    running.snapshot = {
        "document": {"nodes": [node("llm", "llm")], "edges": []},
        "order": ["llm"],
        "budget": {"plan": {"llm": ".1"}, "limit_yuan": "3"},
    }
    running.save()
    error = GatewayError("HTTP 401")
    error.http_status = 401
    with (
        patch("core.management.commands.worker.make_script", side_effect=error),
        pytest.raises(GatewayError),
    ):
        run_flow(running)
    assert running.remote_state["node_states"]["llm"]["submission_state"] == "rejected"


def test_explicit_video_auth_rejection_is_not_unknown(running):
    from core.video_api import generate, provider_snapshot

    provider = Provider.objects.create(
        user=running.user,
        name="fixture",
        service="video",
        model="fixture",
        base_url="https://example.com",
        encrypted_key=encrypt("fixture"),
        video_config={**DEFAULT_CONFIG, "mode": "sync"},
    )
    running.remote_state = {"flow": True, "node_states": {}, "completed": {}}
    running._node_key = "video"
    running.save()
    error = GatewayError("HTTP 401")
    error.http_status = 401
    with (
        patch("core.video_api.transport", side_effect=error),
        pytest.raises(GatewayError),
    ):
        generate(
            running,
            {
                "video_provider": provider_snapshot(running.user, provider.id),
                "prompt": "test",
            },
        )
    assert node_state(running)["submission_state"] == "rejected"


def test_budgeted_canvas_same_revision_is_idempotent(context):
    user, _, client = context
    provider = Provider.objects.create(
        user=user,
        name="fixture",
        service="image",
        model="doubao-seedream-5-0-flash",
        base_url="https://www.autodl.art/api/v1",
        encrypted_key=encrypt("fixture"),
        video_config={**DEFAULT_CONFIG, "mode": "sync"},
    )
    project = CanvasProject.objects.create(
        user=user,
        name="fixture",
        document={
            "nodes": [
                node(
                    "image",
                    "image_api",
                    provider_id=provider.id,
                    text="adult character",
                )
            ],
            "edges": [],
        },
    )
    one = client.post(
        f"/api/canvases/{project.id}/run/",
        {
            "revision": 1,
            "idempotency_key": "first",
            "confirm_paid": True,
            "budget_limit_yuan": 3,
        },
        content_type="application/json",
    )
    two = client.post(
        f"/api/canvases/{project.id}/run/",
        {
            "revision": 1,
            "idempotency_key": "second",
            "confirm_paid": True,
            "budget_limit_yuan": 3,
        },
        content_type="application/json",
    )
    assert one.status_code == two.status_code == 202
    assert one.json()["id"] == two.json()["id"]
    assert Job.objects.count() == 1


def test_saved_audio_canvas_reopens_and_saves(context):
    user, _, client = context
    audio = Asset.objects.create(
        user=user, name="female narration.wav", kind="audio", path="female.wav",
        sha256="a" * 64, size=100, metadata={"duration": 10},
    )
    doc = {
        "nodes": [node("audio", "audio", entity_id=audio.id),
                  node("video", "video_api"), node("mix", "voiceover"),
                  node("result", "result")],
        "edges": [edge("audio", "mix"), edge("video", "mix"), edge("mix", "result")],
    }
    project = CanvasProject.objects.create(user=user, name="female edit", document=doc)
    loaded = client.get(f"/api/canvases/{project.id}/")
    assert loaded.status_code == 200
    saved = client.put(
        f"/api/canvases/{project.id}/", loaded.json(), content_type="application/json"
    )
    assert saved.status_code == 200
    assert saved.json()["document"] == doc
    assert saved.json()["revision"] == 2
    assert Job.objects.count() == 0


@pytest.mark.parametrize("edges", [
    [edge("story", "audio")],
    [edge("audio", "mix"), {**edge("audio", "mix"), "id": "duplicate"}],
])
def test_audio_voiceover_support_still_rejects_invalid_edges(context, edges):
    doc = {"nodes": [node("story", "llm"), node("audio", "audio"),
                     node("mix", "voiceover")], "edges": edges}
    with pytest.raises(ValidationError, match="非法或重复连线"):
        graph_validate(doc, context[0])
