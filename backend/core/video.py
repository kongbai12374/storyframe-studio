import os, signal, subprocess, time, json, shutil, uuid
from pathlib import Path
from django.conf import settings
from rest_framework.exceptions import ValidationError
from .models import Asset, Job, Profile
from .queue import update_job, resource_check, log
from .storage import safe_path, probe
from .gateway import tts


class Cancelled(Exception):
    pass


def check(job):
    status = (
        Job.objects.filter(pk=job.pk, lease_owner=job.lease_owner)
        .values_list("status", flat=True)
        .first()
    )
    if status != "running":
        raise Cancelled()
    if time.monotonic() - job._start > 900:
        raise TimeoutError("任务超过15分钟")


def run_process(job, args, folder):
    logfile = folder / "process.log"
    with open(logfile, "wb") as output:
        proc = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=output, start_new_session=True
        )
        try:
            while proc.poll() is None:
                check(job)
                update_job(job)
                if logfile.stat().st_size > 1024 * 1024:
                    raise RuntimeError("媒体处理日志超出限制")
                resource_check()
                time.sleep(0.5)
            check(job)
            if proc.returncode:
                raise RuntimeError(
                    "媒体处理失败，请检查素材格式；错误码" + str(proc.returncode)
                )
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()


def ass_time(seconds):
    cs = round(seconds * 100)
    return f"{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}"


def ass_text(text):
    return (
        text.replace("\\", "＼")
        .replace("{", "｛")
        .replace("}", "｝")
        .replace("\r", "")
        .replace("\n", r"\N")
    )


def compose(job, snapshot):
    from django.db.models import Sum

    scenes = snapshot["scenes"]
    tmp = settings.MEDIA_ROOT / "tmp" / str(job.id)
    tmp.mkdir(parents=True, exist_ok=True)
    output_dir = settings.MEDIA_ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)
    final = output_dir / (uuid.uuid4().hex + ".mp4")
    segments = []
    try:
        for i, scene in enumerate(scenes):
            check(job)
            update_job(
                job,
                stage=f"分镜 {i+1}/{len(scenes)}",
                progress=5 + int(i / len(scenes) * 75),
            )
            image = Asset.objects.get(id=scene["image_id"], user=job.user, kind="image")
            image_path = safe_path(image.path)
            duration = float(scene["duration"])
            audio_path = None
            if scene.get("audio_id"):
                audio = Asset.objects.get(
                    id=scene["audio_id"], user=job.user, kind="audio"
                )
                audio_path = safe_path(audio.path)
                if audio.metadata["duration"] > duration + 0.15:
                    raise ValueError(f"分镜{i+1}音频超过画面时长，请调整分镜")
            elif snapshot.get("use_tts") and scene.get("dialogue"):
                update_job(job, stage=f"配音 {i+1}")
                check(job)
                audio_path = tmp / f"audio{i}.wav"
                audio_path.write_bytes(tts(job.user, scene["dialogue"]))
                check(job)
                if float(probe(audio_path)["format"]["duration"]) > duration + 0.15:
                    raise ValueError("生成的配音超过分镜时长，请调整后重试")
            subtitle = tmp / f"sub{i}.ass"
            subtitle.write_text(
                "[Script Info]\nScriptType: v4.00+\nPlayResX: 1280\nPlayResY: 720\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Noto Sans CJK SC,36,&H00FFFFFF,&H000000FF,&H00151515,&H70000000,0,0,0,0,100,100,0,0,1,2,0,2,60,60,40,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,"
                + ass_time(duration)
                + ",Default,,0,0,0,,"
                + ass_text(scene.get("dialogue", ""))
                + "\n",
                encoding="utf-8",
            )
            segment = tmp / f"clip{i}.mp4"
            frames = round(duration * 24)
            vf = f"scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,zoompan=z='min(zoom+0.00012,1.04)':d=1:s=1280x720:fps=24,ass={subtitle}"
            args = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-threads",
                "1",
                "-filter_threads",
                "1",
                "-loop",
                "1",
                "-framerate",
                "24",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(image_path),
            ]
            if audio_path:
                args += ["-protocol_whitelist", "file,pipe", "-i", str(audio_path)]
            else:
                args += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
            args += [
                "-vf",
                vf,
                "-af",
                "apad",
                "-t",
                str(duration),
                "-r",
                "24",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "24",
                "-threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(segment),
            ]
            run_process(job, args, tmp)
            segments.append(segment)
        update_job(job, stage="拼接成片", progress=85)
        manifest = tmp / "concat.txt"
        manifest.write_text("".join("file '" + str(p) + "'\n" for p in segments))
        temp_output = tmp / "final.mp4"
        run_process(
            job,
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(manifest),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(temp_output),
            ],
            tmp,
        )
        info = probe(temp_output)
        video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
        audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
        total = sum(s["duration"] for s in scenes)
        if (
            not video
            or video["codec_name"] != "h264"
            or video["width"] != 1280
            or video["height"] != 720
            or not audio
            or abs(float(info["format"]["duration"]) - total) > 1
        ):
            raise ValueError("输出媒体验证失败")
        profile, _ = Profile.objects.get_or_create(user=job.user)
        from .storage import used_bytes

        used = used_bytes(job.user)
        if used + temp_output.stat().st_size > profile.quota_bytes:
            raise ValueError("成片超过存储配额")
        check(job)
        os.replace(temp_output, final)
        return {
            "path": str(final.relative_to(settings.MEDIA_ROOT)),
            "size": final.stat().st_size,
            "duration": float(info["format"]["duration"]),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
