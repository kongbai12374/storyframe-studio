"""Bounded image result ingestion using the same private asset pipeline as uploads."""

import base64
import binascii
import io
import time
from urllib.parse import urlsplit, urlunsplit
from PIL import Image, UnidentifiedImageError
from django.core.files.uploadedfile import SimpleUploadedFile
from .gateway import public_target, PinnedHTTPS, decrypt, GatewayError
from .storage import save_upload
from .video import check
from .queue import resource_check

MAX_IMAGE = 10 * 1024 * 1024


def fetch_image(job, provider, frozen, url):
    if not isinstance(url, str) or len(url) > 12000:
        raise GatewayError("图片直链格式无效")
    parts = urlsplit(url)
    if parts.username or parts.password or parts.fragment:
        raise GatewayError("图片直链格式无效")
    parsed, ip = public_target(
        urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    )
    conn = PinnedHTTPS(parsed.hostname, ip)
    conn.timeout = 30
    try:
        headers = {}
        if parts.hostname == urlsplit(frozen["base_url"]).hostname:
            config = frozen["config"]
            headers[config["auth_header"]] = config["auth_prefix"] + decrypt(
                provider.encrypted_key
            )
        conn.request(
            "GET",
            (parts.path or "/") + ("?" + parts.query if parts.query else ""),
            headers=headers,
        )
        response = conn.getresponse()
        if response.status != 200:
            raise GatewayError("图片下载失败或发生重定向，请使用HTTPS图片直链")
        data = bytearray()
        deadline = time.monotonic() + 90
        while True:
            check(job)
            resource_check()
            if time.monotonic() > deadline:
                raise GatewayError("图片下载超时")
            chunk = response.read(min(65536, MAX_IMAGE + 1 - len(data)))
            if not chunk:
                return bytes(data)
            data.extend(chunk)
            if len(data) > MAX_IMAGE:
                raise GatewayError("单张图片最大10MB")
    finally:
        conn.close()


def decode_image(value):
    if not isinstance(value, str) or len(value) > 14 * 1024 * 1024:
        raise GatewayError("图片Base64格式无效或超过10MB")
    if value.startswith("data:"):
        prefix, separator, value = value.partition(",")
        if not separator or prefix not in [
            "data:image/png;base64",
            "data:image/jpeg;base64",
            "data:image/webp;base64",
        ]:
            raise GatewayError("图片Data URL格式无效")
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise GatewayError("图片Base64格式无效")
    if len(data) > MAX_IMAGE:
        raise GatewayError("单张图片最大10MB")
    return data


def save_result(job, provider, frozen, value, count=1):
    values = value if isinstance(value, list) else [value]
    if not 1 <= len(values) <= min(count, 4):
        raise GatewayError("图片结果数量无效，请检查映射字段与生成张数")
    ids = []
    for item in values:
        check(job)
        resource_check()
        if isinstance(item, dict):
            item = (
                item.get("b64_json")
                if frozen["config"]["output_format"] == "base64"
                else item.get("url")
            )
        blob = (
            decode_image(item)
            if frozen["config"]["output_format"] == "base64"
            else fetch_image(job, provider, frozen, item)
        )
        try:
            with Image.open(io.BytesIO(blob)) as image:
                if (
                    image.format not in ["PNG", "JPEG", "WEBP"]
                    or image.width * image.height > 16_000_000
                ):
                    raise GatewayError("仅接收PNG、JPEG、WebP图片，最多1600万像素")
                image.verify()
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
        ):
            raise GatewayError("供应商结果不是有效图片")
        check(job)
        asset = save_upload(
            job.user,
            SimpleUploadedFile(f"AI图片-{job.id}-{len(ids)+1}.png", blob),
            "AI生成",
        )
        ids.append(asset.id)
    return {
        "asset_ids": list(dict.fromkeys(ids)),
        "source": "image_api",
        "remote_id": __import__("core.video_api", fromlist=["node_state"])
        .node_state(job)
        .get("task_id", ""),
    }
