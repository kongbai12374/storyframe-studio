import socket, ipaddress, ssl, http.client, json, time
from urllib.parse import urlsplit
from cryptography.fernet import Fernet
from django.conf import settings
from django.db.models import F
from .models import Provider, Profile, AIRequest
from django.db import transaction
from django.utils import timezone


class GatewayError(Exception):
    pass


def encrypt(value):
    return Fernet(settings.ENCRYPTION_KEY.encode()).encrypt(value.encode()).decode()


def decrypt(value):
    return Fernet(settings.ENCRYPTION_KEY.encode()).decrypt(value.encode()).decode()


def public_target(url):
    try:
        p = urlsplit(url)
        port = p.port
    except (ValueError, AttributeError, TypeError):
        raise GatewayError("服务地址格式错误")
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username
        or p.password
        or p.fragment
        or p.query
        or port not in [None, 443]
    ):
        raise GatewayError("仅允许HTTPS公网地址及443端口")
    try:
        ips = list(
            dict.fromkeys(
                x[4][0]
                for x in socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
            )
        )
    except OSError:
        raise GatewayError("无法解析供应商域名")
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise GatewayError("目标地址不在允许的公网范围")
    return p, ips[0]


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip):
        super().__init__(host, 443, timeout=60, context=ssl.create_default_context())
        self.ip = ip

    def connect(self):
        self.sock = self._context.wrap_socket(
            socket.create_connection((self.ip, 443), timeout=self.timeout),
            server_hostname=self.host,
        )


def request_provider(provider, endpoint, body, limit=20 * 1024 * 1024):
    p, ip = public_target(provider.base_url)
    profile, _ = Profile.objects.get_or_create(user=provider.user)
    with transaction.atomic():
        if not Profile.objects.filter(pk=profile.pk, api_calls_remaining__gt=0).update(
            api_calls_remaining=F("api_calls_remaining") - 1
        ):
            raise GatewayError("API调用额度不足")
        audit = AIRequest.objects.create(
            user=provider.user,
            provider=provider,
            service=provider.service,
            endpoint=endpoint,
        )
    conn = PinnedHTTPS(p.hostname, ip)
    try:
        conn.request(
            "POST",
            p.path.rstrip("/") + "/" + endpoint,
            body=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + decrypt(provider.encrypted_key),
                "Content-Type": "application/json",
            },
        )
        response = conn.getresponse()
        data = bytearray()
        deadline = time.monotonic() + 90
        while True:
            if time.monotonic() > deadline:
                raise GatewayError("供应商响应超时，结果未知，请核查额度后重试")
            chunk = response.read(min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > limit:
                raise GatewayError("供应商响应超过大小限制")
        audit.http_status = response.status
        if response.status != 200:
            audit.status = "failed"
            error = GatewayError("供应商拒绝请求，HTTP " + str(response.status))
            error.http_status = response.status
            raise error
        audit.status = "succeeded"
        return bytes(data)
    except (OSError, http.client.HTTPException):
        raise GatewayError("供应商连接异常，结果未知；不会自动重发付费请求")
    finally:
        conn.close()
        if audit.status == "submitted":
            audit.status = "unknown"
        audit.completed_at = timezone.now()
        audit.save(update_fields=["status", "http_status", "completed_at"])


def provider_for(user, service):
    p = (
        Provider.objects.filter(user=user, service=service, active=True)
        .order_by("id")
        .first()
    )
    if not p:
        raise GatewayError("尚未配置" + service.upper() + "服务，请先到API配置添加")
    return p


def llm(user, synopsis, style):
    from .models import PromptTemplate

    template = PromptTemplate.objects.filter(name=style).first()
    prompt = (
        (template.prompt if template else "编写适合短视频的中文剧本。")
        + " 只返回JSON对象，字段title与scenes。scenes为1至12项，字段description、dialogue、duration(1至60秒)，总时长最多60秒。"
    )
    p = provider_for(user, "llm")
    raw = request_provider(
        p,
        "chat/completions",
        {
            "model": p.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": synopsis},
            ],
            "max_tokens": 1800,
            **(
                {"thinking": {"type": "disabled"}}
                if urlsplit(p.base_url).hostname == "api.deepseek.com"
                else {}
            ),
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        },
        512 * 1024,
    )
    try:
        return json.loads(json.loads(raw)["choices"][0]["message"]["content"])
    except (KeyError, ValueError, IndexError, TypeError):
        raise GatewayError("模型没有返回有效的结构化剧本")


def tts(user, text):
    p = provider_for(user, "tts")
    return request_provider(
        p,
        "audio/speech",
        {"model": p.model, "input": text, "voice": "alloy", "response_format": "wav"},
    )
