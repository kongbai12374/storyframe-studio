import fcntl, os, time, uuid, signal, shutil, threading
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from django.db import OperationalError, close_old_connections
from core.models import Job, WorkerHeartbeat, Script, Asset
from core.queue import claim, update_job, log, resource_check
from core.video import compose, Cancelled, check
from core.gateway import llm, tts, GatewayError
from core.video_api import generate as generate_video
from core.validation import scenes_validate, require_text
from core.storage import save_upload, safe_path
from django.core.files.uploadedfile import SimpleUploadedFile


def make_script(job, synopsis, style):
    check(job)
    result = llm(job.user, synopsis, style)
    check(job)
    scenes = scenes_validate(result.get("scenes"), job.user)
    obj = Script.objects.create(
        user=job.user,
        title=require_text(result.get("title"), "title"),
        synopsis=synopsis,
        style=style,
        scenes=scenes,
    )
    return {
        "script_id": obj.id,
        "title": obj.title,
        "scenes": scenes,
        "revision": obj.revision,
    }


def run_canvas(job):
    snap = job.snapshot
    if any(
        n.get("data", {}).get("kind") in ["image_api", "voiceover"]
        for n in snap["document"]["nodes"]
    ):
        from core.canvas_flow import run_flow

        return run_flow(job)
    nodes = {n["id"]: n for n in snap["document"]["nodes"]}
    results = {}
    last = {}
    for number, ident in enumerate(snap["order"]):
        check(job)
        data = nodes[ident]["data"]
        kind = data["kind"]
        inputs = [
            results[e["source"]]
            for e in snap["document"]["edges"]
            if e["target"] == ident and e["source"] in results
        ]
        value = dict(snap["entities"].get(ident, {}))
        update_job(
            job,
            stage="画布 · " + data.get("label", kind),
            progress=int(number / len(snap["order"]) * 90),
        )
        log(job, "执行节点 " + data.get("label", kind))
        if kind == "llm":
            value = make_script(job, data.get("text", "") or "创作一个短故事", "甜宠")
        elif kind == "tts":
            text = data.get("text", "") or "\n".join(
                s.get("dialogue", "") for v in inputs for s in v.get("scenes", [])
            )
            if not text:
                raise ValueError("TTS节点没有配音文本")
            blob = tts(job.user, text)
            check(job)
            asset = save_upload(job.user, SimpleUploadedFile("tts.wav", blob))
            value = {"asset_id": asset.id, "audio_id": asset.id}
        elif kind in ["script", "scene"]:
            for v in inputs:
                if "scenes" in v and not value:
                    value = dict(v)
            if "scenes" in value:
                value["scenes"] = [dict(s) for s in value["scenes"]]
                for v in inputs:
                    if v.get("asset_id"):
                        asset = Asset.objects.get(id=v["asset_id"], user=job.user)
                        for s in value["scenes"]:
                            s["image_id" if asset.kind == "image" else "audio_id"] = (
                                asset.id
                            )
        elif kind == "video_api":
            for v in inputs:
                if "scenes" in v:
                    value = dict(v)
            prompt = data.get("text", "") or "\n".join(
                s.get("description", "") + " " + s.get("dialogue", "")
                for s in value.get("scenes", [])
            )
            if not prompt.strip():
                raise ValueError("API视频节点需要提示词或输入剧本")
            images = list(
                dict.fromkeys(
                    v["asset_id"]
                    for v in inputs
                    if v.get("asset_id")
                    and Asset.objects.get(pk=v["asset_id"], user=job.user).kind
                    == "image"
                )
            )
            if len(images) > 9:
                raise ValueError("API视频最多连接9张参考图")
            snapshot = {
                "video_provider": snap["video_providers"][ident],
                "prompt": prompt[:4000],
                "seconds": data.get("seconds", 5),
                "size": data.get("size", "1280x720"),
                "image_ids": images,
            }
            if snap.get("resume_remote_state"):
                snapshot["resume_remote_state"] = snap["resume_remote_state"]
            value = generate_video(job, snapshot)
            last = value
        elif kind == "compose":
            for v in inputs:
                if "scenes" in v:
                    value = dict(v)
            if not value.get("scenes"):
                raise ValueError("合成节点需要连接剧本或选择剧本")
            value["scenes"] = [dict(s) for s in value["scenes"]]
            for v in inputs:
                if v.get("asset_id"):
                    a = Asset.objects.get(id=v["asset_id"], user=job.user)
                    for s in value["scenes"]:
                        key = "image_id" if a.kind == "image" else "audio_id"
                        if not s.get(key):
                            s[key] = a.id
            if any(not s.get("image_id") for s in value["scenes"]):
                raise ValueError("每个分镜都需要图片")
            value = compose(job, value)
            last = value
        elif kind == "result":
            if inputs:
                value = dict(inputs[-1])
        results[ident] = value
        check(job)
    return {
        **last,
        "nodes": {
            k: {a: b for a, b in v.items() if a not in ["path", "scenes"]}
            for k, v in results.items()
        },
    }


class Command(BaseCommand):
    help = "Single persistent queue worker"

    def handle(self, *args, **options):
        lock = open(settings.DATA_DIR / "worker.lock", "a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("另一个worker已在运行")
        self.stop = False

        def stop(*_):
            self.stop = True
            Job.objects.filter(lease_owner=owner, status="running").update(
                status="cancel_requested"
            )

        owner = uuid.uuid4().hex
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        Job.objects.filter(status__in=["running", "cancel_requested"]).update(
            status="interrupted",
            stage="执行进程中断，请检查后手动重试",
            error_code="worker_interrupted",
            completed_at=timezone.now(),
        )
        for folder in (
            (settings.MEDIA_ROOT / "tmp").glob("*")
            if (settings.MEDIA_ROOT / "tmp").exists()
            else []
        ):
            if folder.is_dir():
                shutil.rmtree(folder, ignore_errors=True)

        def heartbeat():
            while not self.stop:
                try:
                    close_old_connections()
                    WorkerHeartbeat.objects.update_or_create(
                        name="main", defaults={"updated_at": timezone.now()}
                    )
                    Job.objects.filter(
                        lease_owner=owner, status__in=["running", "cancel_requested"]
                    ).update(heartbeat_at=timezone.now())
                except OperationalError:
                    pass
                time.sleep(3)

        threading.Thread(target=heartbeat, daemon=True).start()
        last_cleanup = 0
        while not self.stop:
            if time.monotonic() - last_cleanup > 60:
                from core.cleanup import cleanup_stale

                cleanup_stale()
                last_cleanup = time.monotonic()
            close_old_connections()
            WorkerHeartbeat.objects.update_or_create(
                name="main", defaults={"updated_at": timezone.now()}
            )
            try:
                resource_check()
                job = claim(owner)
            except (OperationalError, Exception) as e:
                self.stderr.write("任务领取暂停：" + type(e).__name__)
                time.sleep(3)
                continue
            if not job:
                time.sleep(1)
                continue
            job._start = time.monotonic()
            result = {}
            try:
                log(job, "任务开始")
                if job.kind == "compose":
                    result = compose(job, job.snapshot)
                elif job.kind in ["video_api", "image_api"]:
                    result = generate_video(job, job.snapshot)
                elif job.kind == "llm":
                    result = make_script(
                        job, job.snapshot["synopsis"], job.snapshot["style"]
                    )
                elif job.kind == "canvas":
                    result = run_canvas(job)
                else:
                    raise ValueError("未知任务类型")
                check(job)
                if not update_job(
                    job,
                    status="succeeded",
                    stage="已完成",
                    progress=100,
                    result=result,
                    completed_at=timezone.now(),
                ):
                    raise Cancelled()
                log(job, "任务完成")
            except Cancelled:
                if result.get("path"):
                    safe_path(result["path"]).unlink(missing_ok=True)
                Job.objects.filter(
                    pk=job.pk,
                    lease_owner=owner,
                    status__in=["running", "cancel_requested"],
                ).update(
                    status="cancelled", stage="已取消", completed_at=timezone.now()
                )
                log(job, "任务已取消")
            except Exception as e:
                message = (
                    str(e)[:300]
                    if isinstance(e, (ValueError, GatewayError, TimeoutError))
                    else "任务处理失败：" + type(e).__name__
                )
                if "密钥" in message:
                    message = "AI配置无法读取，请检查加密配置"
                Job.objects.filter(
                    pk=job.pk,
                    lease_owner=owner,
                    status__in=["running", "cancel_requested"],
                ).update(
                    status="failed",
                    stage="失败",
                    error=message,
                    error_code=type(e).__name__,
                    completed_at=timezone.now(),
                )
                log(job, message)
            WorkerHeartbeat.objects.update_or_create(
                name="main", defaults={"updated_at": timezone.now()}
            )
