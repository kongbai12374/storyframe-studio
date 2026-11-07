import json, uuid, mimetypes, copy
from pathlib import Path
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidation
from django.db import transaction
from django.db.models import F, Sum
from django.http import FileResponse, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, NotFound
from .models import (
    Script,
    Asset,
    Provider,
    CanvasProject,
    Job,
    Profile,
    PromptTemplate,
    WorkerHeartbeat,
)
from .serializers import (
    ScriptSerializer,
    AssetSerializer,
    ProviderSerializer,
    CanvasSerializer,
    JobSerializer,
)
from .validation import scenes_validate, graph_validate, require_text
from .video_api import (
    validate_config,
    provider_snapshot,
    prepare_snapshot,
    prepare_image_snapshot,
)
from .gateway import encrypt, public_target, GatewayError
from .queue import enqueue, ACTIVE
from .storage import save_upload, safe_path


def asset_referenced(value, ident):
    if isinstance(value, dict):
        return any(
            (key in ["image_id", "audio_id", "asset_id"] and item == ident)
            or (
                key in ["image_ids", "asset_ids"]
                and isinstance(item, list)
                and ident in item
            )
            or asset_referenced(item, ident)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(asset_referenced(item, ident) for item in value)
    return False


def owned(model, ident, user):
    try:
        return model.objects.get(pk=ident, user=user)
    except (model.DoesNotExist, ValueError, TypeError):
        raise NotFound("对象不存在或无权限")


def profile_data(user):
    p, _ = Profile.objects.get_or_create(user=user)
    from .storage import used_bytes

    used = used_bytes(user)
    return {
        "id": user.id,
        "username": user.username,
        "name": user.first_name,
        "is_admin": user.is_staff,
        "quota_bytes": p.quota_bytes,
        "used_bytes": used,
        "api_calls_remaining": p.api_calls_remaining,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    return Response({"csrfToken": get_token(request)})


@require_POST
@csrf_protect
def signin(request):
    from django.core.cache import cache

    key = "login:" + request.META.get("REMOTE_ADDR", "")
    n = cache.get(key, 0)
    if n >= 20:
        return JsonResponse({"detail": "登录尝试过于频繁，请稍后再试"}, status=429)
    cache.set(key, n + 1, 60)
    try:
        body = json.loads(request.body)
    except (ValueError, UnicodeError):
        return JsonResponse({"detail": "请求格式错误"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"detail": "请求格式错误"}, status=400)
    user = authenticate(
        request,
        username=str(body.get("username", ""))[:150],
        password=str(body.get("password", ""))[:256],
    )
    if not user:
        return JsonResponse({"detail": "账号或密码错误"}, status=400)
    login(request, user)
    return JsonResponse(profile_data(user))


@api_view(["POST"])
def signout(request):
    logout(request)
    return Response({"ok": True})


@api_view(["GET", "PATCH"])
def me(request):
    if request.method == "PATCH":
        user = request.user
        if "password" in request.data:
            if not user.check_password(request.data.get("old_password", "")):
                raise ValidationError({"old_password": "原密码错误"})
            try:
                validate_password(request.data["password"], user)
            except DjangoValidation as e:
                raise ValidationError({"password": e.messages})
            user.set_password(request.data["password"])
            user.save()
            update_session_auth_hash(request, user)
        if "name" in request.data:
            user.first_name = str(request.data["name"])[:80]
            user.save(update_fields=["first_name"])
    return Response(profile_data(request.user))


def page(query, request, serializer):
    try:
        n = max(1, min(int(request.query_params.get("page", 1)), 100000))
        limit = max(1, min(int(request.query_params.get("limit", 20)), 100))
    except (ValueError, TypeError):
        raise ValidationError("分页参数无效")
    return Response(
        {
            "results": serializer(query[(n - 1) * limit : n * limit], many=True).data,
            "total": query.count(),
            "page": n,
            "limit": limit,
        }
    )


@api_view(["GET", "POST"])
def scripts(request):
    if request.method == "GET":
        return page(
            Script.objects.filter(
                user=request.user,
                title__icontains=request.query_params.get("q", "")[:160],
            ).order_by("-id"),
            request,
            ScriptSerializer,
        )
    s = ScriptSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    scenes = scenes_validate(
        request.data.get("scenes", [{"duration": 5}]), request.user
    )
    obj = s.save(user=request.user, scenes=scenes)
    return Response(ScriptSerializer(obj).data, status=201)


@api_view(["GET", "PUT", "DELETE"])
def script_detail(request, ident):
    obj = owned(Script, ident, request.user)
    if request.method == "DELETE":
        for project in CanvasProject.objects.filter(user=request.user):
            if any(
                n.get("data", {}).get("entity_id") == obj.id
                and n.get("data", {}).get("kind")
                in ["script", "scene", "compose", "llm", "video_api"]
                for n in project.document.get("nodes", [])
            ):
                return Response(
                    {"detail": "剧本仍被画布引用，请先解除关联"}, status=409
                )
        obj.delete()
        return Response(status=204)
    if request.method == "PUT":
        s = ScriptSerializer(obj, data=request.data)
        s.is_valid(raise_exception=True)
        scenes = scenes_validate(request.data.get("scenes"), request.user)
        if request.data.get("revision") != obj.revision:
            return Response({"detail": "剧本已被修改，请重新载入"}, status=409)
        with transaction.atomic():
            n = (
                Script.objects.filter(pk=obj.pk, revision=obj.revision).update(
                    **s.validated_data,
                    scenes=scenes,
                    revision=F("revision") + 1,
                    updated_at=timezone.now(),
                )
                if "scenes" not in s.validated_data
                else Script.objects.filter(pk=obj.pk, revision=obj.revision).update(
                    **{**s.validated_data, "scenes": scenes},
                    revision=F("revision") + 1,
                    updated_at=timezone.now(),
                )
            )
            if not n:
                return Response({"detail": "剧本版本冲突"}, status=409)
        obj.refresh_from_db()
    return Response(ScriptSerializer(obj).data)


@api_view(["POST"])
def duplicate_script(request, ident):
    obj = owned(Script, ident, request.user)
    obj.pk = None
    obj.title = (obj.title + " 副本")[:160]
    obj.revision = 1
    obj.save()
    return Response(ScriptSerializer(obj).data, status=201)


@api_view(["GET"])
def export_script(request, ident):
    obj = owned(Script, ident, request.user)
    text = "# " + obj.title + "\n\n" + obj.synopsis
    for i, s in enumerate(obj.scenes):
        text += f'\n\n## 分镜 {i+1} · {s["duration"]}秒\n{s["description"]}\n\n{s["dialogue"]}'
    response = HttpResponse(text, content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="script.md"'
    return response


@api_view(["GET", "POST"])
def assets(request):
    if request.method == "POST":
        return Response(
            AssetSerializer(
                save_upload(
                    request.user,
                    request.FILES.get("file"),
                    request.data.get("tags", ""),
                )
            ).data,
            status=201,
        )
    query = Asset.objects.filter(
        user=request.user, name__icontains=request.query_params.get("q", "")[:160]
    ).order_by("-id")
    if request.query_params.get("kind"):
        query = query.filter(kind=request.query_params["kind"])
    if request.query_params.get("tag"):
        query = query.filter(tags__icontains=request.query_params["tag"][:100])
    return page(query, request, AssetSerializer)


@api_view(["GET", "DELETE", "PATCH"])
def asset_detail(request, ident):
    obj = owned(Asset, ident, request.user)
    if request.method == "DELETE":
        for script in Script.objects.filter(user=request.user):
            if any(
                obj.id in [s.get("image_id"), s.get("audio_id")] for s in script.scenes
            ):
                return Response(
                    {"detail": "素材仍被剧本引用，请先解除关联"}, status=409
                )
        for job in Job.objects.filter(user=request.user, status__in=ACTIVE):
            if asset_referenced(job.snapshot, obj.id) or asset_referenced(
                job.remote_state, obj.id
            ):
                return Response({"detail": "任务执行中暂不能删除素材"}, status=409)
        for project in CanvasProject.objects.filter(user=request.user):
            if any(
                n.get("data", {}).get("entity_id") == obj.id
                and n.get("data", {}).get("kind") in ["image", "audio", "tts"]
                for n in project.document.get("nodes", [])
            ):
                return Response({"detail": "素材仍被画布引用"}, status=409)
        path = safe_path(obj.path)
        thumb = safe_path(obj.thumbnail) if obj.thumbnail else None
        obj.delete()
        path.unlink(missing_ok=True)
        if thumb:
            thumb.unlink(missing_ok=True)
        return Response(status=204)
    if request.method == "PATCH":
        obj.tags = str(request.data.get("tags", ""))[:200]
        obj.save(update_fields=["tags"])
    return Response(AssetSerializer(obj).data)


@api_view(["GET"])
def asset_file(request, ident):
    obj = owned(Asset, ident, request.user)
    path = safe_path(
        obj.thumbnail
        if request.query_params.get("thumbnail") and obj.thumbnail
        else obj.path
    )
    if not path.exists():
        raise NotFound("文件不存在")
    response = FileResponse(
        path.open("rb"),
        content_type=(
            "image/jpeg"
            if obj.kind == "image"
            else "audio/wav" if obj.name.lower().endswith(".wav") else "audio/mpeg"
        ),
    )
    response["Cache-Control"] = "private, max-age=60"
    return response


@api_view(["GET", "POST"])
def providers(request):
    if request.method == "GET":
        return Response(
            ProviderSerializer(
                Provider.objects.filter(user=request.user), many=True
            ).data
        )
    return save_provider(request)


def save_provider(request, obj=None):
    data = request.data
    service = data.get("service", obj.service if obj else "")
    if service not in ["llm", "tts", "video", "image"]:
        raise ValidationError({"service": "请选择LLM、TTS、图片或视频生成服务"})
    base = data.get("base_url", obj.base_url if obj else "")
    try:
        public_target(base)
    except (GatewayError, ValueError):
        raise ValidationError({"base_url": "请输入有效的HTTPS公网服务地址"})
    name = require_text(data.get("name", obj.name if obj else ""), "name", 80)
    model = require_text(data.get("model", obj.model if obj else ""), "model", 100)
    if not obj:
        obj = Provider(user=request.user)
    key = data.get("api_key")
    if key:
        if not isinstance(key, str) or len(key) > 1000:
            raise ValidationError({"api_key": "密钥格式无效"})
        obj.encrypted_key = encrypt(key)
        obj.key_tail = key[-4:]
    if not obj.encrypted_key:
        raise ValidationError({"api_key": "首次配置需要密钥"})
    if (
        obj.pk
        and (obj.service in ["video", "image"] or service in ["video", "image"])
        and Job.objects.filter(user=request.user, status__in=ACTIVE).exists()
    ):
        return Response({"detail": "存在活动任务，暂不能修改视频API配置"}, status=409)
    if service in ["video", "image"] or service == "tts" and data.get("video_config"):
        obj.video_config = validate_config(
            data.get("video_config", obj.video_config or {})
        )
    if service == "tts" and data.get("video_config") == {}:
        obj.video_config = {}
    obj.name = name
    obj.model = model
    obj.service = service
    obj.base_url = base
    obj.active = data.get("active", True) is True
    obj.save()
    return Response(ProviderSerializer(obj).data, status=200)


@api_view(["PUT", "DELETE"])
def provider_detail(request, ident):
    obj = owned(Provider, ident, request.user)
    if request.method == "DELETE":
        if (
            obj.service in ["video", "image"]
            and Job.objects.filter(user=request.user, status__in=ACTIVE).exists()
        ):
            return Response(
                {"detail": "存在活动任务，暂不能删除视频API配置"}, status=409
            )
        obj.delete()
        return Response(status=204)
    return save_provider(request, obj)


@api_view(["POST"])
def provider_test(request, ident):
    obj = owned(Provider, ident, request.user)
    try:
        public_target(obj.base_url)
    except GatewayError:
        raise ValidationError("服务地址无法解析或不符合公网策略")
    return Response(
        {
            "detail": "地址解析与密钥解密检查通过；此检查不发送付费请求，不代表供应商鉴权或模型调用成功",
            "key_readable": bool(
                __import__("core.gateway", fromlist=["decrypt"]).decrypt(
                    obj.encrypted_key
                )
            ),
        }
    )


@api_view(["GET", "POST"])
def canvases(request):
    if request.method == "GET":
        return page(
            CanvasProject.objects.filter(user=request.user).order_by("-id"),
            request,
            CanvasSerializer,
        )
    name = require_text(request.data.get("name", "未命名画布"), "name")
    obj = CanvasProject.objects.create(
        user=request.user,
        name=name,
        document={"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}},
    )
    return Response(CanvasSerializer(obj).data, status=201)


@api_view(["GET", "PUT", "DELETE"])
def canvas_detail(request, ident):
    obj = owned(CanvasProject, ident, request.user)
    if request.method == "DELETE":
        obj.delete()
        return Response(status=204)
    if request.method == "PUT":
        doc = request.data.get("document")
        graph_validate(doc, request.user)
        name = require_text(request.data.get("name", obj.name), "name")
        n = CanvasProject.objects.filter(
            pk=obj.pk, revision=request.data.get("revision")
        ).update(
            document=doc,
            name=name,
            revision=F("revision") + 1,
            updated_at=timezone.now(),
        )
        if not n:
            return Response(
                {"detail": "画布已在其他页面更新，请重新载入或另存副本"}, status=409
            )
        obj.refresh_from_db()
    return Response(CanvasSerializer(obj).data)


def canvas_snapshot(obj, user, selected=None):
    doc = copy.deepcopy(obj.document)
    order = graph_validate(doc, user)
    nodes = {n["id"]: n for n in doc["nodes"]}
    if selected:
        if not isinstance(selected, list) or any(n not in nodes for n in selected):
            raise ValidationError("选中的节点无效")
        wanted = set(selected)
        for n in reversed(order):
            if n in wanted:
                wanted.update(e["source"] for e in doc["edges"] if e["target"] == n)
        order = [n for n in order if n in wanted]
    if sum(nodes[n]["data"]["kind"] in ["compose", "video_api"] for n in order) > 1:
        raise ValidationError("轻量版每次流程只允许一个视频合成节点，请分别执行")
    entities = {}
    video_providers = {}
    for ident in order:
        data = nodes[ident]["data"]
        kind = data["kind"]
        entity = data.get("entity_id")
        if kind in ["script", "scene", "compose", "video_api"] and entity:
            script = owned(Script, entity, user)
            entities[ident] = {
                "script_id": script.id,
                "revision": script.revision,
                "title": script.title,
                "scenes": scenes_validate(script.scenes, user),
            }
        if (
            kind in ["video_api", "image_api"]
            or kind == "tts"
            and data.get("provider_id")
        ):
            video_providers[ident] = provider_snapshot(
                user,
                data.get("provider_id"),
                "image" if kind == "image_api" else "tts" if kind == "tts" else "video",
            )
        if kind == "tts" and entity:
            entities[ident] = {"asset_id": owned(Asset, entity, user).id}
        elif kind in ["image", "audio"] and entity:
            entities[ident] = {"asset_id": owned(Asset, entity, user).id}
    if not order or not any(
        nodes[n]["data"]["kind"]
        in ["compose", "llm", "tts", "video_api", "image_api", "voiceover"]
        for n in order
    ):
        raise ValidationError("至少添加一个合成、AI剧本或TTS执行节点")
    return {
        "project_id": obj.id,
        "revision": obj.revision,
        "document": doc,
        "order": order,
        "entities": entities,
        "use_tts": False,
        "video_providers": video_providers,
    }


@api_view(["POST"])
def canvas_run(request, ident):
    obj = owned(CanvasProject, ident, request.user)
    if request.data.get("revision") != obj.revision:
        return Response({"detail": "请先保存或重新载入画布"}, status=409)
    snapshot = canvas_snapshot(obj, request.user, request.data.get("selected"))
    if any(
        n["data"]["kind"] in ["image_api", "voiceover"]
        for n in snapshot["document"]["nodes"]
    ):
        from .canvas_flow import validate_budget

        if request.data.get("budget_limit_yuan") is not None and any(
            n["data"]["kind"] == "llm" for n in snapshot["document"]["nodes"]
        ):
            from .gateway import provider_for

            p = provider_for(request.user, "llm")
            if p.base_url != "https://api.deepseek.com" or p.model != "deepseek-flash":
                raise ValidationError("预算内AI剧本执行仅支持已核价的DeepSeek Flash")
        snapshot["budget"] = validate_budget(
            snapshot, request.data.get("budget_limit_yuan")
        )
    if snapshot.get("video_providers") and request.data.get("confirm_paid") is not True:
        raise ValidationError("执行视频API可能产生费用，请明确确认")
    execution_key = request.data.get("idempotency_key")
    if snapshot.get("budget", {}).get("limit_yuan") is not None:
        execution_key = (
            f"canvas-budget:{obj.id}:{obj.revision}:{snapshot['budget']['limit_yuan']}"
        )
    job = enqueue(request.user, "canvas", snapshot, execution_key)
    return Response(JobSerializer(job).data, status=202)


@api_view(["GET", "POST"])
def jobs(request):
    if request.method == "GET":
        return page(
            Job.objects.filter(user=request.user).order_by("-id"),
            request,
            JobSerializer,
        )
    kind = request.data.get("kind", "compose")
    if kind == "llm":
        snapshot = {
            "synopsis": require_text(request.data.get("synopsis"), "synopsis", 4000),
            "style": request.data.get("style", "甜宠"),
        }
    elif kind in ["video_api", "image_api"]:
        if request.data.get("confirm_paid") is not True:
            raise ValidationError("提交生成API可能产生费用，请明确确认")
        snapshot = (
            prepare_image_snapshot if kind == "image_api" else prepare_snapshot
        )(request.user, request.data)
    elif kind == "compose":
        script = owned(Script, request.data.get("script_id"), request.user)
        scenes = scenes_validate(script.scenes, request.user)
        if any(not s["image_id"] for s in scenes):
            raise ValidationError("每个分镜都需要选择图片")
        if any(
            s.get("audio_id")
            and owned(Asset, s["audio_id"], request.user).metadata.get("duration", 0)
            > s["duration"] + 0.15
            for s in scenes
        ):
            raise ValidationError("音频超过对应分镜时长")
        snapshot = {
            "script_id": script.id,
            "revision": script.revision,
            "title": script.title,
            "scenes": scenes,
            "use_tts": request.data.get("use_tts") is True,
        }
    else:
        raise ValidationError("任务类型无效")
    job = enqueue(request.user, kind, snapshot, request.data.get("idempotency_key"))
    return Response(JobSerializer(job).data, status=202)


@api_view(["GET", "DELETE"])
def job_detail(request, ident):
    obj = owned(Job, ident, request.user)
    if request.method == "DELETE":
        with transaction.atomic():
            obj = Job.objects.select_for_update().get(pk=obj.pk)
            if obj.status in ACTIVE:
                return Response(
                    {"detail": "请先取消任务并等待停止，再删除"}, status=409
                )
            for canvas in CanvasProject.objects.filter(user=request.user):
                if any(
                    n.get("data", {}).get("kind") == "result"
                    and n.get("data", {}).get("entity_id") == obj.id
                    for n in canvas.document.get("nodes", [])
                ):
                    return Response(
                        {"detail": "任务仍被画布结果节点引用，请先解除关联"}, status=409
                    )
            from .storage import job_output_files

            files = set(job_output_files(obj))
            for other in Job.objects.filter(user=request.user).exclude(pk=obj.pk):
                files.difference_update(job_output_files(other))
                resume = other.snapshot.get("resume_remote_state", {})
                files.difference_update(
                    v.get("path")
                    for v in resume.get("completed", {}).values()
                    if isinstance(v, dict) and v.get("path")
                )
            paths = [safe_path(path) for path in files]
            obj.delete()
            for path in paths:
                transaction.on_commit(lambda path=path: path.unlink(missing_ok=True))
        return Response(status=204)
    data = JobSerializer(obj).data
    data["logs"] = list(obj.logs.order_by("-id").values("message", "created_at")[:100])
    return Response(data)


@api_view(["POST"])
def job_cancel(request, ident):
    obj = owned(Job, ident, request.user)
    with transaction.atomic():
        Job.objects.filter(pk=obj.pk, status="queued").update(
            status="cancelled", stage="已取消", completed_at=timezone.now()
        )
        Job.objects.filter(pk=obj.pk, status="running").update(
            status="cancel_requested", stage="正在取消"
        )
    obj.refresh_from_db()
    return Response(JobSerializer(obj).data)


@api_view(["POST"])
def job_retry(request, ident):
    obj = owned(Job, ident, request.user)
    if obj.status not in ["failed", "interrupted", "cancelled"]:
        raise ValidationError("只有失败、中断或取消任务可重试")
    if (obj.kind != "compose" or obj.snapshot.get("use_tts")) and not request.data.get(
        "confirm_paid"
    ):
        raise ValidationError("该任务可能产生付费调用，请核查后显式确认重试")
    snapshot = copy.deepcopy(obj.snapshot)
    if (
        obj.kind in ["video_api", "image_api"]
        or obj.kind == "canvas"
        and obj.remote_state
    ):
        if request.data.get("new_generation") is True:
            snapshot.pop("resume_remote_state", None)
            if obj.kind in ["video_api", "image_api"]:
                snapshot["video_provider"] = provider_snapshot(
                    request.user,
                    snapshot.get("video_provider", {}).get("provider_id"),
                    "image" if obj.kind == "image_api" else "video",
                )
            elif obj.kind == "canvas":
                snapshot["video_providers"] = {
                    node: provider_snapshot(request.user, config.get("provider_id"))
                    for node, config in snapshot.get("video_providers", {}).items()
                }
        elif obj.kind == "canvas" and obj.remote_state.get("flow"):
            snapshot["resume_remote_state"] = copy.deepcopy(obj.remote_state)
        elif obj.remote_state.get("task_id"):
            snapshot["resume_remote_state"] = copy.deepcopy(obj.remote_state)
        elif obj.remote_state.get("submission_state") in ["sending", "accepted"]:
            raise ValidationError(
                "原提交结果未知，请先核查供应商；重新生成需显式new_generation确认"
            )
    return Response(
        JobSerializer(
            enqueue(
                request.user,
                obj.kind,
                snapshot,
                request.data.get("idempotency_key"),
            )
        ).data,
        status=202,
    )


@api_view(["GET"])
def job_download(request, ident):
    obj = owned(Job, ident, request.user)
    if obj.status != "succeeded" or not obj.result.get("path"):
        raise NotFound("成片尚未生成")
    path = safe_path(obj.result["path"])
    if not path.exists():
        raise NotFound("成片文件不存在")
    return FileResponse(
        path.open("rb"),
        content_type="video/mp4",
        as_attachment=request.query_params.get("download") == "1",
        filename="drama.mp4",
    )


@api_view(["GET"])
def dashboard(request):
    from collections import Counter

    jobs = Job.objects.filter(user=request.user)
    return Response(
        {
            "scripts": Script.objects.filter(user=request.user).count(),
            "assets": Asset.objects.filter(user=request.user).count(),
            "canvases": CanvasProject.objects.filter(user=request.user).count(),
            "jobs": dict(Counter(jobs.values_list("status", flat=True))),
            "profile": profile_data(request.user),
        }
    )


@require_GET
def health(request):
    worker = WorkerHeartbeat.objects.filter(name="main").first()
    fresh = bool(worker and (timezone.now() - worker.updated_at).total_seconds() < 20)
    return JsonResponse(
        {"status": "ok" if fresh else "degraded", "worker": fresh},
        status=200 if fresh else 503,
    )


def spa(request, path=""):
    if path.startswith(("api/", "media/")):
        return JsonResponse({"detail": "Not found"}, status=404)
    from django.views.static import serve

    candidate = settings.FRONTEND_DIR / path
    if (
        path
        and candidate.is_file()
        and candidate.resolve().is_relative_to(settings.FRONTEND_DIR.resolve())
    ):
        return serve(request, path, document_root=settings.FRONTEND_DIR)
    index = settings.FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index.open("rb"), content_type="text/html")
    return HttpResponse("前端尚未构建", status=503)
