"""User-configurable HTTPS/JSON video adapter. No implicit paid resubmission."""

import base64
import copy
import json
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, quote
from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import Provider, Profile, AIRequest, Job, Asset
from .gateway import public_target, PinnedHTTPS, decrypt, GatewayError
from .queue import update_job, resource_check, log
from .storage import safe_path, probe
from .video import check, Cancelled

DEFAULT_CONFIG = {
    "mode": "async",
    "submit_path": "/videos",
    "poll_path": "/videos/{{task_id}}",
    "cancel_path": "",
    "cancel_method": "POST",
    "content_path": "",
    "auth_header": "Authorization",
    "auth_prefix": "Bearer ",
    "request_body": {
        "model": "{{model}}",
        "prompt": "{{prompt}}",
        "duration": "{{seconds}}",
        "size": "{{size}}",
    },
    "task_id_field": "id",
    "status_field": "status",
    "progress_field": "progress",
    "video_url_field": "video_url",
    "success_values": ["completed", "succeeded", "success"],
    "failure_values": ["failed", "error", "cancelled", "canceled"],
    "poll_seconds": 5,
    "output_format": "url",
}
PLACEHOLDERS = {
    "model",
    "prompt",
    "seconds",
    "size",
    "image_base64",
    "image_data_url",
    "images_base64",
    "images_data_urls",
    "count",
    "text",
    "audio_url",
    "images_urls",
    *{f"image_url_{i}" for i in range(9)},
}
SECRET_FIELDS = {
    "api_key",
    "apikey",
    "access_token",
    "token",
    "secret",
    "password",
    "authorization",
}
FORBIDDEN_HEADERS = {
    "host",
    "content-length",
    "content-type",
    "connection",
    "transfer-encoding",
    "cookie",
    "proxy-authorization",
}


def relative_path(value, allow_task=False):
    if (
        not isinstance(value, str)
        or len(value) > 400
        or not value.startswith("/")
        or value.startswith("//")
        or any(ord(c) < 33 or c == "\\" for c in value)
    ):
        raise ValidationError("接口路径必须为以 / 开头的相对路径")
    if any(x in value for x in ["..", "#", "://"]):
        raise ValidationError("接口路径无效")
    if "{{" in value and (
        not allow_task
        or value.count("{{task_id}}") != 1
        or "{{" in value.replace("{{task_id}}", "")
    ):
        raise ValidationError("路径仅支持 {{task_id}} 占位符")
    if urlsplit(value).netloc:
        raise ValidationError("路径不得替换供应商域名")
    return value


def validate_config(raw):
    if (
        not isinstance(raw, dict)
        or len(json.dumps(raw, ensure_ascii=False).encode()) > 32768
        or set(raw) - set(DEFAULT_CONFIG)
    ):
        raise ValidationError("视频映射配置无效或超过32KB")
    config = {**copy.deepcopy(DEFAULT_CONFIG), **raw}
    if config["mode"] not in ["async", "sync"]:
        raise ValidationError("mode只能是async或sync")
    if config["output_format"] not in ["url", "base64"]:
        raise ValidationError("output_format只能是url或base64")
    relative_path(config["submit_path"])
    if config["mode"] == "async":
        relative_path(config["poll_path"], True)
    for key in ["cancel_path", "content_path"]:
        if config[key]:
            relative_path(config[key], True)
    if config["cancel_method"] not in ["POST", "DELETE"]:
        raise ValidationError("取消方法仅支持POST/DELETE")
    if (
        not isinstance(config["auth_header"], str)
        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,63}", config["auth_header"])
        or config["auth_header"].lower() in FORBIDDEN_HEADERS
    ):
        raise ValidationError("鉴权头名称无效")
    if (
        not isinstance(config["auth_prefix"], str)
        or len(config["auth_prefix"]) > 30
        or any(ord(c) < 32 or ord(c) > 126 for c in config["auth_prefix"])
    ):
        raise ValidationError("鉴权前缀无效")
    for key in ["task_id_field", "status_field", "progress_field", "video_url_field"]:
        value = config[key]
        if (
            not isinstance(value, str)
            or len(value) > 120
            or not re.fullmatch(r"[A-Za-z0-9_.]*", value)
        ):
            raise ValidationError(
                "结果字段使用点分隔路径，例如 data.video_url 或 data.0.url"
            )
    for key in ["success_values", "failure_values"]:
        if (
            not isinstance(config[key], list)
            or not 1 <= len(config[key]) <= 20
            or any(not isinstance(x, str) or not 1 <= len(x) <= 40 for x in config[key])
        ):
            raise ValidationError("状态枚举须为短字符串列表")
    if set(x.lower() for x in config["success_values"]) & set(
        x.lower() for x in config["failure_values"]
    ):
        raise ValidationError("成功与失败状态不能重叠")
    if type(config["poll_seconds"]) is not int or not 3 <= config["poll_seconds"] <= 30:
        raise ValidationError("轮询间隔须为3–30秒")

    def scan(value, depth=0):
        if depth > 10:
            raise ValidationError("请求模板嵌套过深")
        if isinstance(value, dict):
            for k, v in value.items():
                if k.lower() in SECRET_FIELDS:
                    raise ValidationError(
                        "密钥只允许填写在专用API Key字段，不要写进JSON映射"
                    )
                scan(v, depth + 1)
        elif isinstance(value, list):
            for v in value:
                scan(v, depth + 1)
        elif isinstance(value, str):
            if len(value) > 8000:
                raise ValidationError("模板文字过长")
            if any(v not in PLACEHOLDERS for v in re.findall(r"{{([^{}]+)}}", value)):
                raise ValidationError("请求模板包含未知占位符")
        elif value is not None and type(value) not in [int, float, bool]:
            raise ValidationError("请求模板包含无效数据")

    if not isinstance(config["request_body"], dict):
        raise ValidationError("request_body须为JSON对象")
    scan(config["request_body"])
    return config


def extract(data, path, default=None):
    if not path:
        return default
    for part in path.split("."):
        try:
            data = data[int(part)] if isinstance(data, list) else data[part]
        except (KeyError, IndexError, TypeError, ValueError):
            return default
    return data


def render(value, variables):
    if isinstance(value, dict):
        return {k: render(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, variables) for v in value]
    if isinstance(value, str):
        whole = re.fullmatch(r"{{([^{}]+)}}", value)
        if whole:
            return variables.get(whole[1], "")
        return re.sub(r"{{([^{}]+)}}", lambda m: str(variables.get(m[1], "")), value)
    return value


def provider_snapshot(user, ident=None, service="video"):
    query = Provider.objects.filter(user=user, service=service, active=True)
    provider = query.filter(pk=ident).first() if ident else query.order_by("id").first()
    if not provider:
        raise ValidationError("请先添加并启用对应的图片或视频生成API服务")
    return {
        "provider_id": provider.id,
        "base_url": provider.base_url,
        "model": provider.model,
        "config": validate_config(provider.video_config),
        "service": service,
    }


def prepare_snapshot(user, data):
    from .validation import require_text

    prompt = require_text(data.get("prompt"), "prompt", 4000)
    seconds = data.get("seconds", 5)
    if type(seconds) is not int or not 1 <= seconds <= 60:
        raise ValidationError("视频时长须为1–60整数秒，供应商需支持该时长")
    if data.get("size", "1280x720") not in ["1280x720", "720x1280"]:
        raise ValidationError("仅支持720p横屏或竖屏")
    images = validate_images(user, data)
    image = images[0] if images else None
    if image and not Asset.objects.filter(pk=image, user=user, kind="image").exists():
        raise ValidationError("参考图片不存在或无权限")
    return {
        "video_provider": provider_snapshot(user, data.get("provider_id")),
        "prompt": prompt,
        "seconds": seconds,
        "size": data.get("size", "1280x720"),
        "image_id": image or None,
        "image_ids": images,
    }


def validate_images(user, data):
    images = data.get("image_ids", [data["image_id"]] if data.get("image_id") else [])
    if (
        not isinstance(images, list)
        or len(images) > 9
        or any(type(x) is not int or x < 1 for x in images)
        or len(set(images)) != len(images)
    ):
        raise ValidationError("参考图须为不重复的图片ID列表，最多9张")
    if Asset.objects.filter(pk__in=images, user=user, kind="image").count() != len(
        images
    ):
        raise ValidationError("参考图片不存在或无权限")
    return images


def prepare_image_snapshot(user, data):
    from .validation import require_text

    size = data.get("size", "1024x1024")
    if not isinstance(size, str) or not re.fullmatch(
        r"[1-9][0-9]{1,3}x[1-9][0-9]{1,3}|auto", size
    ):
        raise ValidationError("图片尺寸使用宽x高或auto，具体支持范围以供应商为准")
    count = data.get("count", 1)
    if type(count) is not int or not 1 <= count <= 4:
        raise ValidationError("每次生成1–4张图片")
    return {
        "video_provider": provider_snapshot(user, data.get("provider_id"), "image"),
        "prompt": require_text(data.get("prompt"), "prompt", 4000),
        "size": size,
        "count": count,
    }


def node_state(job):
    key = getattr(job, "_node_key", None)
    return (
        job.remote_state.get("node_states", {}).get(key, {})
        if key
        else job.remote_state
    )


def persist(job, state):
    if getattr(job, "_node_key", None):
        envelope = copy.deepcopy(job.remote_state)
        envelope.setdefault("node_states", {})[job._node_key] = copy.deepcopy(state)
        state = envelope
    if not Job.objects.filter(
        pk=job.pk,
        lease_owner=job.lease_owner,
        status__in=["running", "cancel_requested"],
    ).update(remote_state=copy.deepcopy(state), heartbeat_at=timezone.now()):
        raise Cancelled()
    job.remote_state = copy.deepcopy(state)


def transport(job, provider, snapshot, path, method="GET", body=None, charge=False):
    """Pinned HTTPS, bounded JSON; polling does not deduct generation quota."""
    relative_path(path)
    parsed, ip = public_target(snapshot["base_url"])
    config = snapshot["config"]
    audit = None
    if charge:
        with transaction.atomic():
            profile, _ = Profile.objects.get_or_create(user=job.user)
            if not Profile.objects.filter(
                pk=profile.pk, api_calls_remaining__gt=0
            ).update(api_calls_remaining=F("api_calls_remaining") - 1):
                raise GatewayError("API调用额度不足")
            audit = AIRequest.objects.create(
                user=job.user,
                provider=provider,
                service=snapshot.get("service", "video"),
                endpoint=snapshot.get("service", "video") + ".submit",
            )
    conn = PinnedHTTPS(parsed.hostname, ip)
    conn.timeout = 30
    try:
        headers = {
            config["auth_header"]: config["auth_prefix"]
            + decrypt(provider.encrypted_key),
            "Accept": "application/json",
        }
        payload = None
        if body is not None:
            payload = json.dumps(body, allow_nan=False).encode()
            headers["Content-Type"] = "application/json"
        conn.timeout = 120 if snapshot.get("service") == "image" else 30
        conn.request(
            method, parsed.path.rstrip("/") + path, body=payload, headers=headers
        )
        response = conn.getresponse()
        result = bytearray()
        maximum = (
            24 * 1024 * 1024 if snapshot.get("service") == "image" else 1024 * 1024
        )
        deadline = time.monotonic() + 150
        while True:
            if time.monotonic() > deadline:
                raise GatewayError("生成接口响应超时，提交结果可能未知，请勿重复生成")
            chunk = response.read(min(65536, maximum + 1 - len(result)))
            if not chunk:
                break
            result.extend(chunk)
            if len(result) > maximum:
                raise GatewayError("生成接口JSON响应超过大小限制")
        if audit:
            audit.http_status = response.status
        if response.status not in [200, 201, 202]:
            if audit:
                audit.status = "failed"
            detail = ""
            try:
                failure = json.loads(result)
                candidate = failure.get(
                    "error", failure.get("message", failure.get("msg", ""))
                )
                if isinstance(candidate, dict):
                    candidate = candidate.get("message", candidate.get("code", ""))
                if isinstance(candidate, str):
                    detail = candidate.replace(
                        decrypt(provider.encrypted_key), "[密钥已隐藏]"
                    )
                    detail = re.sub(r"https?://[^\s]+", "[地址已隐藏]", detail)
                    detail = re.sub(r"sk-[A-Za-z0-9_-]{10,}", "[密钥已隐藏]", detail)[
                        :180
                    ]
            except (ValueError, TypeError, AttributeError):
                pass
            error = GatewayError(
                "生成供应商返回HTTP "
                + str(response.status)
                + ("：" + detail if detail else "")
            )
            error.http_status = response.status
            raise error
        try:
            data = json.loads(result)
        except (ValueError, UnicodeError):
            raise GatewayError("生成接口未返回有效JSON，请检查协议映射")
        if not isinstance(data, dict):
            raise GatewayError("生成接口JSON顶层必须为对象")
        if audit:
            audit.status = "succeeded"
        return data
    except (
        OSError,
        __import__("http.client", fromlist=["HTTPException"]).HTTPException,
    ):
        raise GatewayError("视频服务连接中断，结果可能未知；不会自动重复提交付费任务")
    finally:
        conn.close()
        if audit:
            if audit.status == "submitted":
                audit.status = "unknown"
            audit.completed_at = timezone.now()
            audit.save(update_fields=["status", "http_status", "completed_at"])


def download(job, provider, snapshot, url):
    """Stream an authenticated same-origin result or public CDN, never leak keys cross-origin."""
    parts = urlsplit(url)
    if parts.username or parts.password or parts.fragment:
        raise GatewayError("成片地址无效")
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    parsed, ip = public_target(clean)
    if len(url) > 12000:
        raise GatewayError("成片地址过长")
    folder = settings.MEDIA_ROOT / "outputs"
    folder.mkdir(exist_ok=True)
    target = folder / (uuid.uuid4().hex + ".mp4")
    temp = target.with_suffix(".part")
    config = snapshot["config"]
    conn = PinnedHTTPS(parsed.hostname, ip)
    conn.timeout = 30
    try:
        headers = {}
        origin = urlsplit(snapshot["base_url"])
        if parts.hostname == origin.hostname:
            headers[config["auth_header"]] = config["auth_prefix"] + decrypt(
                provider.encrypted_key
            )
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        if response.status != 200:
            raise GatewayError("成片下载失败或发生重定向，请检查直链配置")
        profile, _ = Profile.objects.get_or_create(user=job.user)
        from .storage import used_bytes

        used = used_bytes(job.user)
        maximum = min(100 * 1024 * 1024, max(0, profile.quota_bytes - used))
        count = 0
        deadline = time.monotonic() + 180
        with temp.open("wb") as output:
            while True:
                check(job)
                resource_check()
                if time.monotonic() > deadline:
                    raise GatewayError("成片下载超时，可查询原任务后重新下载")
                chunk = response.read(65536)
                if not chunk:
                    break
                count += len(chunk)
                if count > maximum:
                    raise GatewayError("成片超过100MB限制或用户存储配额")
                output.write(chunk)
                update_job(job, stage="正在保存API成片", progress=95)
        info = probe(temp)
        video = next(
            (x for x in info.get("streams", []) if x.get("codec_type") == "video"), None
        )
        duration = float(info.get("format", {}).get("duration", 0))
        if (
            "mp4" not in info.get("format", {}).get("format_name", "")
            or not video
            or not 0 < duration <= 61
            or video.get("width", 0) > 2048
            or video.get("height", 0) > 2048
        ):
            raise GatewayError("成片媒体验证失败（最长60秒、分辨率最大2048）")
        check(job)
        temp.replace(target)
        return {
            "path": str(target.relative_to(settings.MEDIA_ROOT)),
            "size": count,
            "duration": duration,
            "source": "video_api",
            "remote_id": node_state(job).get("task_id", ""),
        }
    except Exception:
        temp.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise
    finally:
        conn.close()


def generate(job, snapshot):
    frozen = snapshot["video_provider"]
    media_name = "图片" if frozen.get("service") == "image" else "视频"
    config = frozen["config"]
    try:
        provider = Provider.objects.get(
            pk=frozen["provider_id"],
            user=job.user,
            service=frozen.get("service", "video"),
        )
    except Provider.DoesNotExist:
        raise GatewayError("原视频API配置已不存在")
    state = copy.deepcopy(node_state(job) or snapshot.get("resume_remote_state") or {})
    response = None
    if state.get("submission_state") in ["sending", "accepted"] and not state.get(
        "task_id"
    ):
        raise GatewayError("之前的提交结果未知，请先核查供应商记录；平台不会重复提交")
    try:
        check(job)
        if not state.get("task_id"):
            variables = {
                "model": frozen["model"],
                "prompt": snapshot["prompt"],
                "seconds": snapshot.get("seconds", 5),
                "size": snapshot.get("size", "1280x720"),
                "image_base64": "",
                "image_data_url": "",
                "images_base64": [],
                "images_data_urls": [],
                "count": snapshot.get("count", 1),
                "text": snapshot.get("prompt", ""),
                "audio_url": "",
                "images_urls": [],
                **{f"image_url_{i}": "" for i in range(9)},
            }
            images = validate_images(job.user, snapshot)
            for image_id in images:
                image = Asset.objects.get(pk=image_id, user=job.user, kind="image")
                variables["images_base64"].append(
                    base64.b64encode(safe_path(image.path).read_bytes()).decode()
                )
            variables["images_data_urls"] = [
                "data:image/jpeg;base64," + x for x in variables["images_base64"]
            ]
            if images:
                variables["image_base64"] = variables["images_base64"][0]
                variables["image_data_url"] = variables["images_data_urls"][0]
            template = json.dumps(config["request_body"])
            if any(token in template for token in ["{{image_url_", "{{images_urls}}"]):
                from .asset_links import asset_link

                urls = [asset_link(job.user, ident) for ident in images]
                variables["images_urls"] = urls
                variables.update(
                    {f"image_url_{i}": value for i, value in enumerate(urls)}
                )
            if "{{audio_url}}" in template:
                from .asset_links import asset_link

                if not Asset.objects.filter(
                    pk=snapshot.get("audio_id"), user=job.user, kind="audio"
                ).exists():
                    raise GatewayError("TTS需要选择参考音频素材")
                variables["audio_url"] = asset_link(job.user, snapshot["audio_id"])
            state = {
                "provider_id": provider.id,
                "submission_state": "sending",
                "status": "submitting",
            }
            persist(job, state)
            update_job(
                job, stage="正在向用户配置的API提交" + media_name + "任务", progress=5
            )
            response = transport(
                job,
                provider,
                frozen,
                config["submit_path"],
                "POST",
                render(config["request_body"], variables),
                charge=True,
            )
            task_id = extract(response, config["task_id_field"])
            if task_id is not None:
                if (
                    not isinstance(task_id, (str, int))
                    or not 1 <= len(str(task_id)) <= 200
                ):
                    raise GatewayError("供应商任务ID格式不符合配置")
                state["task_id"] = str(task_id)
            state["submission_state"] = "accepted"
            persist(job, state)
            if config["mode"] == "async" and not state.get("task_id"):
                detail = str(response.get("msg", response.get("message", "")))
                detail = detail.replace(decrypt(provider.encrypted_key), "[密钥已隐藏]")
                detail = re.sub(r"https?://[^\s]+", "[地址已隐藏]", detail)[:180]
                state["response_code"] = str(response.get("code", ""))[:80]
                state["response_message"] = detail
                persist(job, state)
                raise GatewayError(
                    "未能取得供应商任务ID"
                    + ("：" + detail if detail else "，请检查task_id_field")
                    + "；未自动重复提交"
                )
            log(job, "生成任务已提交供应商；后续查询不会再次提交生成请求")
        else:
            log(job, "恢复查询原供应商任务，不重新提交视频生成请求")
        deadline = time.monotonic() + 720
        while True:
            check(job)
            resource_check()
            if response is None:
                path = config["poll_path"].replace(
                    "{{task_id}}", quote(state["task_id"], safe="")
                )
                response = transport(job, provider, frozen, path)
            raw_status = extract(response, config["status_field"], "")
            status = str(raw_status).lower()
            state["status"] = status[:80]
            persist(job, state)
            if status in [x.lower() for x in config["failure_values"]]:
                raise GatewayError("供应商生成任务失败或被取消，请在供应商侧核查原因")
            url = extract(response, config["video_url_field"])
            done = config["mode"] == "sync" or status in [
                x.lower() for x in config["success_values"]
            ]
            if done:
                if not url and config["content_path"] and state.get("task_id"):
                    base = frozen["base_url"].rstrip("/")
                    url = base + config["content_path"].replace(
                        "{{task_id}}", quote(state["task_id"], safe="")
                    )
                if frozen.get("service") == "tts":
                    from .audio_api import save_result as save_audio_result

                    result = save_audio_result(job, provider, frozen, url)
                    state["status"] = "completed"
                    persist(job, state)
                    return result
                if frozen.get("service") == "image":
                    from .image_api import save_result

                    result = save_result(
                        job, provider, frozen, url, snapshot.get("count", 1)
                    )
                    state["status"] = "completed"
                    persist(job, state)
                    return result
                if not isinstance(url, str) or not url:
                    raise GatewayError(
                        "供应商已完成，但未找到成片URL，请检查video_url_field或content_path"
                    )
                update_job(job, stage="视频API生成完成，验证并保存成片", progress=92)
                result = download(job, provider, frozen, url)
                state["status"] = "completed"
                persist(job, state)
                return result
            if config["mode"] == "sync":
                raise GatewayError("同步接口没有返回成片URL")
            progress = extract(response, config["progress_field"], 0)
            try:
                progress = max(5, min(90, int(float(progress))))
            except (ValueError, TypeError, OverflowError):
                progress = 10
            update_job(job, stage="供应商正在生成" + media_name, progress=progress)
            if time.monotonic() > deadline:
                raise GatewayError(
                    "供应商任务仍未结束，已保存原任务ID，可稍后查询原任务"
                )
            for _ in range(config["poll_seconds"]):
                check(job)
                time.sleep(1)
            response = None
    except GatewayError as error:
        if state.get("submission_state") == "sending" and getattr(
            error, "http_status", None
        ) in [400, 401, 402, 403, 404, 405, 422]:
            state.update(
                submission_state="rejected",
                status="failed",
                http_status=error.http_status,
            )
            persist(job, state)
        raise
    except Cancelled:
        if state.get("task_id") and config["cancel_path"]:
            try:
                transport(
                    job,
                    provider,
                    frozen,
                    config["cancel_path"].replace(
                        "{{task_id}}", quote(state["task_id"], safe="")
                    ),
                    config["cancel_method"],
                    {} if config["cancel_method"] == "POST" else None,
                )
                state["cancellation"] = "cancel_requested_at_provider"
            except Exception:
                state["cancellation"] = "provider_cancel_unconfirmed"
        else:
            state["cancellation"] = "local_cancel_only_provider_may_continue"
        persist(job, state)
        log(job, "本地任务已取消；供应商是否停止及费用以供应商记录为准")
        raise
