"""Serial canvas execution with paid-node checkpoints and conservative budget reservations."""

import copy
import time
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError
from .models import Asset, Script, Profile
from .queue import log, update_job
from .video import check, run_process
from .storage import safe_path, save_upload, probe, used_bytes
from .video_api import generate, persist
from .gateway import GatewayError, tts


def validate_budget(snapshot, raw_limit=None):
    try:
        limit = Decimal(str(raw_limit)) if raw_limit is not None else None
        if limit is not None and (
            not limit.is_finite() or not Decimal("0.01") <= limit <= 100
        ):
            raise ValueError()
    except (ValueError, InvalidOperation):
        raise ValidationError("预算须为0.01–100元")
    plan = {}
    for node in snapshot["document"]["nodes"]:
        ident = node["id"]
        data = node["data"]
        kind = data["kind"]
        if ident not in snapshot["order"]:
            continue
        provider = snapshot.get("video_providers", {}).get(ident, {})
        model = provider.get("model", "")
        known = True
        if kind == "llm":
            cost = Decimal("0.10")
        elif kind == "image_api":
            cost = Decimal("0.25") if model == "Z-Image-Turbo" else Decimal("0.15")
            known = model in [
                "doubao-seedream-5-0-flash",
                "Z-Image-Turbo",
            ] and provider.get("base_url", "").startswith("https://www.autodl.art/")
        elif kind == "tts":
            cost = Decimal("0.10")
            known = model == "indextts2-v1" and "autodl.art" in provider.get(
                "base_url", ""
            )
        elif kind == "video_api":
            cost = Decimal("0.07") * data.get("seconds", 5)
            known = model == "minimax_h3_lightx2v_v5_15s" and provider.get(
                "base_url"
            ) in ["https://www.autodl.art", "https://autodl.art"]
        else:
            continue
        if limit is not None and not known:
            raise ValidationError("此服务尚未核价，不能保证预算；请先核实价格")
        plan[ident] = str(cost)
    if limit is not None and sum(map(Decimal, plan.values())) > limit:
        raise ValidationError("保守费用预留超过预算，未提交任何付费请求")
    return {
        "limit_yuan": str(limit) if limit is not None else None,
        "plan": plan,
        "estimated_yuan": str(sum(map(Decimal, plan.values()))),
    }


def store(job):
    key = getattr(job, "_node_key", None)
    if key:
        del job._node_key
    try:
        persist(job, job.remote_state)
    finally:
        if key:
            job._node_key = key


def reserve(job, ident):
    reservations = job.remote_state.setdefault("reservations", {})
    if ident in reservations:
        return
    amount = job.snapshot.get("budget", {}).get("plan", {}).get(ident, "0")
    total = sum(map(Decimal, reservations.values())) + Decimal(amount)
    limit = job.snapshot.get("budget", {}).get("limit_yuan")
    if limit is not None and total > Decimal(limit):
        raise GatewayError("已到预算上限，停止后续付费请求")
    reservations[ident] = amount
    store(job)


def verify_checkpoint(job, value):
    for ident in value.get("asset_ids", []):
        if not Asset.objects.filter(pk=ident, user=job.user).exists():
            raise GatewayError("已完成节点的图片已被删除，停止以免重复收费")
    if (
        value.get("audio_id")
        and not Asset.objects.filter(pk=value["audio_id"], user=job.user).exists()
    ):
        raise GatewayError("已完成节点的配音已被删除")
    if value.get("path") and not safe_path(value["path"]).is_file():
        raise GatewayError("已完成节点的视频文件已被删除")


def voiceover(job, inputs, seconds):
    video = next((v for v in inputs if v.get("path")), None)
    audio = next((v.get("audio_id") for v in inputs if v.get("audio_id")), None)
    if not video or not audio:
        raise GatewayError("配音合成需要同时连接API视频和TTS节点")
    asset = Asset.objects.get(pk=audio, user=job.user, kind="audio")
    duration = asset.metadata.get("duration", 0)
    if duration > seconds * 2:
        raise GatewayError("配音过长，已保留视频和配音，请缩短文本或增加时长")
    profile, _ = Profile.objects.get_or_create(user=job.user)
    if (
        used_bytes(job.user) + min(video.get("size", 0) * 2, 100 * 1024 * 1024)
        > profile.quota_bytes
    ):
        raise GatewayError("成片存储配额不足")
    folder = settings.MEDIA_ROOT / "tmp" / str(job.id) / "voiceover"
    folder.mkdir(parents=True, exist_ok=True)
    target = settings.MEDIA_ROOT / "outputs" / (uuid.uuid4().hex + ".mp4")
    target.parent.mkdir(exist_ok=True)
    speed = max(1, duration / max(seconds - 0.15, 1))
    filters = (f"atempo={speed:.6f}," if speed > 1 else "") + "apad"
    try:
        run_process(
            job,
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(safe_path(video["path"])),
                "-i",
                str(safe_path(asset.path)),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-t",
                str(seconds),
                "-vf",
                "fps=24",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                "-threads",
                "2",
                "-af",
                filters,
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(target),
            ],
            folder,
        )
        info = probe(target)
        return {
            "path": str(target.relative_to(settings.MEDIA_ROOT)),
            "size": target.stat().st_size,
            "duration": float(info["format"]["duration"]),
            "source": "canvas_voiceover",
            "audio_id": audio,
        }
    except Exception:
        target.unlink(missing_ok=True)
        raise


def run_flow(job):
    from .management.commands.worker import make_script

    snap = job.snapshot
    if not job.remote_state:
        job.remote_state = copy.deepcopy(
            snap.get("resume_remote_state")
            or {"flow": True, "node_states": {}, "completed": {}, "reservations": {}}
        )
        store(job)
    completed = job.remote_state.setdefault("completed", {})
    nodes = {n["id"]: n for n in snap["document"]["nodes"]}
    results = {}
    last = {}
    for number, ident in enumerate(snap["order"]):
        job._start = time.monotonic()
        check(job)
        data = nodes[ident]["data"]
        kind = data["kind"]
        if ident in completed:
            verify_checkpoint(job, completed[ident])
            results[ident] = copy.deepcopy(completed[ident])
            continue
        inputs = [
            results[e["source"]]
            for e in snap["document"]["edges"]
            if e["target"] == ident and e["source"] in results
        ]
        script = next((v for v in inputs if v.get("scenes")), {})
        value = copy.deepcopy(snap.get("entities", {}).get(ident, {}))
        log(job, "执行节点 " + data.get("label", kind))
        update_job(
            job,
            stage="画布 · " + data.get("label", kind),
            progress=int(number / max(len(snap["order"]), 1) * 90),
        )
        if kind in ["llm", "image_api", "tts", "video_api"]:
            reserve(job, ident)
        if kind == "llm":
            old = job.remote_state.setdefault("node_states", {}).get(ident, {})
            if old.get("submission_state") == "sending":
                raise GatewayError("AI剧本上次提交结果未知，停止以免重复收费")
            job.remote_state["node_states"][ident] = {"submission_state": "sending"}
            store(job)
            try:
                value = make_script(
                    job, data.get("text") or "创作一个10秒、两个分镜的短故事", "甜宠"
                )
            except GatewayError as error:
                if getattr(error, "http_status", None) in [
                    400,
                    401,
                    402,
                    403,
                    404,
                    405,
                    422,
                ]:
                    job.remote_state["node_states"][ident].update(
                        submission_state="rejected",
                        status="failed",
                        http_status=error.http_status,
                    )
                    store(job)
                raise
        elif kind in ["image_api", "tts", "video_api"]:
            frozen = snap.get("video_providers", {}).get(ident)
            if not frozen:
                raise GatewayError("请选择此节点的API服务")
            prompt = data.get("text", "")
            request = {
                "video_provider": frozen,
                "size": data.get(
                    "size", "2048x2048" if kind == "image_api" else "1280x720"
                ),
                "seconds": data.get("seconds", 10),
                "count": 1,
            }
            if kind == "image_api":
                index = data.get("scene_index", 1) - 1
                if script:
                    if index >= len(script["scenes"]):
                        raise GatewayError("分镜序号超出AI剧本范围")
                    prompt += "\n分镜画面：" + script["scenes"][index]["description"]
                if not prompt.strip():
                    raise GatewayError("文生图需要提示词或AI剧本输入")
            elif kind == "tts":
                prompt = prompt or "".join(
                    s.get("dialogue", "") for s in script.get("scenes", [])
                )
                if not prompt.strip() or len(prompt) > 500:
                    raise GatewayError("配音文本须为1–500字")
                request["audio_id"] = data.get("entity_id")
            else:
                prompt = (
                    prompt
                    + "\n分镜与动作：\n"
                    + "\n".join(
                        s.get("description", "") + " " + s.get("dialogue", "")
                        for s in script.get("scenes", [])
                    )
                ).strip()
                images = []
                for v in inputs:
                    candidates = v.get("asset_ids", []) or (
                        [v["asset_id"]]
                        if v.get("asset_id") and not v.get("audio_id")
                        else []
                    )
                    images.extend(candidates)
                request["image_ids"] = list(dict.fromkeys(images))
            request["prompt"] = prompt.strip()[:4000]
            job._node_key = ident
            try:
                value = generate(job, request)
            finally:
                del job._node_key
            if kind == "image_api":
                value["asset_id"] = value["asset_ids"][0]
                value["scene_index"] = data.get("scene_index", 1)
        elif kind == "voiceover":
            value = voiceover(job, inputs, data.get("seconds", 10))
            last = value
        elif kind in ["script", "scene"]:
            value = value or copy.deepcopy(script)
        elif kind in ["image", "audio"]:
            if value.get("asset_id"):
                asset = Asset.objects.get(pk=value["asset_id"], user=job.user)
                if asset.kind == "audio":
                    value["audio_id"] = asset.id
        elif kind == "result":
            value = copy.deepcopy(inputs[-1] if inputs else {})
        elif kind == "note":
            value = {}
        else:
            raise GatewayError("此全流程中暂不支持该节点类型")
        check(job)
        job.remote_state["completed"][ident] = copy.deepcopy(value)
        # A completed sync node must never be submitted again after restart.
        job.remote_state.setdefault("node_states", {}).setdefault(ident, {})[
            "status"
        ] = "completed"
        store(job)
        results[ident] = value
        if value.get("path"):
            last = value
        log(job, "节点完成 " + data.get("label", kind))
    images = list(
        dict.fromkeys(a for v in results.values() for a in v.get("asset_ids", []))
    )
    script_id = next(
        (v["script_id"] for v in results.values() if v.get("script_id")), None
    )
    return {
        **last,
        "asset_ids": images,
        "script_id": script_id,
        "budget": {
            "limit_yuan": snap.get("budget", {}).get("limit_yuan"),
            "reserved_yuan": str(
                sum(map(Decimal, job.remote_state.get("reservations", {}).values()))
            ),
            "note": "按核价保守预留，实际费用以供应商账单为准",
        },
        "nodes": {
            k: {a: b for a, b in v.items() if a not in ["path", "scenes"]}
            for k, v in results.items()
        },
    }
