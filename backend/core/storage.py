import hashlib, uuid, subprocess, json, os
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError
from .models import Asset, Profile

Image.MAX_IMAGE_PIXELS = 16_000_000


def safe_path(relative):
    root = settings.MEDIA_ROOT.resolve()
    p = (root / relative).resolve()
    if not p.is_relative_to(root):
        raise ValidationError("文件路径无效")
    return p


def probe(path):
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            timeout=10,
            check=True,
        )
        if len(r.stdout) > 65536:
            raise ValueError()
        return json.loads(r.stdout)
    except (ValueError, subprocess.SubprocessError):
        raise ValidationError("媒体文件无法读取")


def save_upload(user, upload, tags=""):
    if not upload or upload.size > 20 * 1024 * 1024:
        raise ValidationError("上传文件最大20MB")
    folder = settings.MEDIA_ROOT / str(user.id)
    folder.mkdir(exist_ok=True)
    relative = str(Path(str(user.id)) / (uuid.uuid4().hex + ".upload"))
    path = safe_path(relative)
    thumb = ""
    digest = hashlib.sha256()
    try:
        size = 0
        with open(path, "wb") as f:
            for chunk in upload.chunks():
                size += len(chunk)
                if size > 20 * 1024 * 1024:
                    raise ValidationError("文件过大")
                digest.update(chunk)
                f.write(chunk)
        existing = Asset.objects.filter(user=user, sha256=digest.hexdigest()).first()
        if existing:
            path.unlink()
            return existing
        try:
            with Image.open(path) as im:
                if (
                    im.format not in ["JPEG", "PNG", "WEBP"]
                    or im.width * im.height > 16_000_000
                    or size > 10 * 1024 * 1024
                ):
                    raise ValidationError("图片格式、尺寸或大小超限")
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((1280, 720))
                meta = {"width": im.width, "height": im.height}
                im.save(str(path) + ".jpg", "JPEG", quality=90)
                im.thumbnail((320, 180))
                im.save(str(path) + ".thumb.jpg", "JPEG")
            path.unlink()
            path = Path(str(path) + ".jpg")
            relative += ".jpg"
            thumb = relative.replace(".jpg", ".thumb.jpg")
            kind = "image"
        except (UnidentifiedImageError, OSError):
            with path.open("rb") as raw:
                header = raw.read(12)
            if not (
                (header[:4] == b"RIFF" and header[8:12] == b"WAVE")
                or header[:3] == b"ID3"
                or len(header) >= 2
                and header[0] == 255
                and header[1] & 224 == 224
            ):
                raise ValidationError("仅支持真实图片、MP3或WAV文件")
            info = probe(path)
            streams = info.get("streams", [])
            if any(x.get("codec_type") == "video" for x in streams) or not any(
                x.get("codec_type") == "audio"
                and x.get("codec_name")
                in ["mp3", "pcm_s16le", "pcm_s24le", "pcm_f32le"]
                for x in streams
            ):
                raise ValidationError("仅支持图片、MP3或WAV音频")
            duration = float(info.get("format", {}).get("duration", 0))
            if not 0 < duration <= 60:
                raise ValidationError("音频最长60秒")
            kind = "audio"
            meta = {"duration": duration}
        with transaction.atomic():
            profile, _ = Profile.objects.get_or_create(user=user)
            used = used_bytes(user)
            stored_size = path.stat().st_size + (
                safe_path(thumb).stat().st_size if thumb else 0
            )
            if used + stored_size > profile.quota_bytes:
                raise ValidationError("存储配额不足")
            return Asset.objects.create(
                user=user,
                name=Path(upload.name).name[:160],
                kind=kind,
                path=relative,
                thumbnail=thumb,
                size=stored_size,
                sha256=digest.hexdigest(),
                metadata=meta,
                tags=str(tags)[:200],
            )
    except Exception as error:
        path.unlink(missing_ok=True)
        Path(str(path) + ".jpg").unlink(missing_ok=True)
        Path(str(path) + ".thumb.jpg").unlink(missing_ok=True)
        if thumb:
            safe_path(thumb).unlink(missing_ok=True)
        if isinstance(error, Image.DecompressionBombError):
            raise ValidationError("图片像素超出安全限制")
        raise


def job_output_files(job):
    values = [job.result] + list(job.remote_state.get("completed", {}).values())
    files = {}
    for value in values:
        if isinstance(value, dict) and value.get("path"):
            files[value["path"]] = int(value.get("size", 0))
    return files


def used_bytes(user):
    from .models import Job

    used = Asset.objects.filter(user=user).aggregate(n=Sum("size"))["n"] or 0
    files = {}
    for job in Job.objects.filter(user=user).only("result", "remote_state", "status"):
        found = job_output_files(job)
        files.update(found)
        if not found and job.status == "succeeded":
            used += int(job.result.get("size", 0))
    return used + sum(files.values())
