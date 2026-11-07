import math, json
from rest_framework.exceptions import ValidationError
from .models import Asset, Script, Job


def require_text(value, label, maximum=160):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValidationError({label: "不能为空或超过长度限制"})
    return value.strip()


def scenes_validate(scenes, user):
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 12:
        raise ValidationError({"scenes": "需要1–12个分镜"})
    total = 0
    clean = []
    for s in scenes:
        if not isinstance(s, dict):
            raise ValidationError({"scenes": "分镜格式错误"})
        duration = s.get("duration", 5)
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(duration)
            or not 1 <= duration <= 60
        ):
            raise ValidationError({"duration": "时长须为1–60秒"})
        total += duration
        t = {
            "description": str(s.get("description", ""))[:2000],
            "dialogue": str(s.get("dialogue", ""))[:1000],
            "duration": duration,
            "image_id": None,
            "audio_id": None,
        }
        for key, kind in [("image_id", "image"), ("audio_id", "audio")]:
            if s.get(key):
                try:
                    a = Asset.objects.get(id=s[key], user=user, kind=kind)
                except (Asset.DoesNotExist, ValueError, TypeError):
                    raise ValidationError({key: "素材不存在或无权限"})
                t[key] = a.id
        clean.append(t)
    if total > 60:
        raise ValidationError({"scenes": "总时长不能超过60秒"})
    return clean


TYPES = {
    "script",
    "scene",
    "image",
    "audio",
    "compose",
    "result",
    "note",
    "llm",
    "tts",
    "video_api",
    "image_api",
    "voiceover",
}
ALLOWED = {
    "script": {"scene", "compose", "video_api", "image_api"},
    "scene": {"compose", "tts", "video_api", "image_api"},
    "image": {"scene", "compose", "video_api"},
    "audio": {"scene", "compose", "voiceover"},
    "llm": {"script", "compose", "video_api", "image_api", "tts"},
    "tts": {"audio", "compose", "voiceover"},
    "compose": {"result"},
    "video_api": {"result", "voiceover"},
    "image_api": {"video_api", "scene", "compose", "result"},
    "voiceover": {"result"},
    "result": set(),
    "note": set(),
}


def graph_validate(doc, user):
    if not isinstance(doc, dict) or set(doc) - {"nodes", "edges", "viewport"}:
        raise ValidationError("画布结构无效")
    if len(json.dumps(doc, ensure_ascii=False).encode()) > 512 * 1024:
        raise ValidationError("画布超过512KB")
    nodes = doc.get("nodes", [])
    edges = doc.get("edges", [])
    if (
        not isinstance(nodes, list)
        or not isinstance(edges, list)
        or len(nodes) > 100
        or len(edges) > 200
    ):
        raise ValidationError("画布最多100节点、200连线")
    types = {}
    counts = {}
    adj = {}
    for n in nodes:
        if not isinstance(n, dict) or set(n) - {"id", "type", "position", "data"}:
            raise ValidationError("节点字段无效")
        ident = n.get("id")
        data = n.get("data", {})
        kind = data.get("kind") if isinstance(data, dict) else None
        if (
            not isinstance(ident, str)
            or not 1 <= len(ident) <= 64
            or ident in types
            or kind not in TYPES
        ):
            raise ValidationError("节点编号或类型无效")
        if set(data) - {
            "kind",
            "label",
            "text",
            "entity_id",
            "provider_id",
            "seconds",
            "size",
            "scene_index",
        }:
            raise ValidationError("禁止在画布保存密钥或未知字段")
        if (
            not isinstance(data.get("label", ""), str)
            or len(data.get("label", "")) > 160
            or not isinstance(data.get("text", ""), str)
            or len(data.get("text", "")) > 4000
        ):
            raise ValidationError("节点文字过长")
        pos = n.get("position", {})
        if not isinstance(pos, dict) or any(
            isinstance(pos.get(k), bool)
            or not isinstance(pos.get(k), (int, float))
            or not math.isfinite(pos[k])
            or abs(pos[k]) > 100000
            for k in ["x", "y"]
        ):
            raise ValidationError("坐标无效")
        if "scene_index" in data and (
            type(data["scene_index"]) is not int or not 1 <= data["scene_index"] <= 12
        ):
            raise ValidationError("分镜序号须为1–12整数")
        if kind in ["image_api", "tts"]:
            from .models import Provider

            if (
                data.get("provider_id")
                and not Provider.objects.filter(
                    pk=data["provider_id"],
                    user=user,
                    service="image" if kind == "image_api" else "tts",
                    active=True,
                ).exists()
            ):
                raise ValidationError("图片或配音服务不存在或无权限")
        if kind == "image_api":
            import re

            if not isinstance(data.get("size", "2048x2048"), str) or not re.fullmatch(
                r"[1-9][0-9]{1,3}x[1-9][0-9]{1,3}|auto", data.get("size", "2048x2048")
            ):
                raise ValidationError("图片尺寸须为宽x高或auto")
        if kind == "voiceover" and (
            type(data.get("seconds", 10)) is not int
            or not 1 <= data.get("seconds", 10) <= 60
        ):
            raise ValidationError("配音成片时长须为1–60整数秒")
        if kind == "video_api":
            from .models import Provider

            if "seconds" in data and (
                type(data["seconds"]) is not int or not 1 <= data["seconds"] <= 60
            ):
                raise ValidationError("API视频时长须为1–60整数秒")
            if data.get("size", "1280x720") not in ["1280x720", "720x1280"]:
                raise ValidationError("API视频尺寸无效")
            if (
                data.get("provider_id")
                and not Provider.objects.filter(
                    pk=data["provider_id"], user=user, service="video", active=True
                ).exists()
            ):
                raise ValidationError("视频API配置不存在或无权限")
        entity = data.get("entity_id")
        if entity:
            model = (
                Script
                if kind in ["script", "scene", "compose", "llm", "video_api"]
                else (
                    Asset
                    if kind in ["image", "audio", "tts"]
                    else Job if kind == "result" else None
                )
            )
            try:
                obj = model.objects.get(id=entity, user=user) if model else None
            except (ValueError, TypeError, model.DoesNotExist if model else ValueError):
                raise ValidationError("引用对象不存在或无权限")
            if not model:
                raise ValidationError("此节点不支持业务引用")
            if kind in ["image", "audio"] and obj.kind != kind:
                raise ValidationError("素材类型不符")
        types[ident] = kind
        counts[ident] = 0
        adj[ident] = []
    seen = set()
    edge_ids = set()
    for e in edges:
        if not isinstance(e, dict) or set(e) - {
            "id",
            "source",
            "target",
            "sourceHandle",
            "targetHandle",
        }:
            raise ValidationError("连线字段无效")
        a = e.get("source")
        b = e.get("target")
        eid = e.get("id")
        if (
            not isinstance(eid, str)
            or eid in edge_ids
            or a not in types
            or b not in types
            or a == b
            or (a, b) in seen
            or types[b] not in ALLOWED[types[a]]
        ):
            raise ValidationError("非法或重复连线")
        edge_ids.add(eid)
        seen.add((a, b))
        counts[b] += 1
        adj[a].append(b)
    queue = [n for n in counts if counts[n] == 0]
    order = []
    while queue:
        a = queue.pop(0)
        order.append(a)
        for b in adj[a]:
            counts[b] -= 1
            if counts[b] == 0:
                queue.append(b)
    if len(order) != len(nodes):
        raise ValidationError("画布不允许循环")
    viewport = doc.get("viewport", {"x": 0, "y": 0, "zoom": 1})
    if (
        not isinstance(viewport, dict)
        or any(
            not isinstance(viewport.get(k), (int, float))
            or not math.isfinite(viewport[k])
            for k in ["x", "y", "zoom"]
        )
        or not 0.1 <= viewport["zoom"] <= 4
    ):
        raise ValidationError("视图无效")
    return order
