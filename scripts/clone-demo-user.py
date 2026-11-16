# -*- coding: utf-8 -*-
"""为演示账号克隆一份可浏览的工作区（画布 / 剧本 / 素材 / 两条成片任务）。

只读来源：admin 的现有数据；写入目标：demo 自己的数据，互不影响。
用法：python /tmp/clone_demo.py [--commit]
"""
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402

from core.models import Asset, CanvasProject, Job, JobLog, Profile, Script  # noqa: E402

COMMIT = "--commit" in sys.argv
DEMO_USER = "demo"
DEMO_PWD = "mirror2026"
QUOTA = 300 * 1024 * 1024
API_CALLS = 20
COPY_JOBS = [25, 23]

U = get_user_model()
MEDIA: Path = Path(settings.MEDIA_ROOT)
admin = U.objects.get(username="admin")
print(f"MEDIA_ROOT = {MEDIA}")
print(f"admin assets={Asset.objects.filter(user=admin).count()} scripts={Script.objects.filter(user=admin).count()}")

if U.objects.filter(username=DEMO_USER).exists():
    print(f"!! 用户 {DEMO_USER} 已存在。如需重建请先删除该用户（会级联删掉其数据）。")
    if COMMIT:
        sys.exit(1)


def remap(o, amap, smap, pmap):
    """递归重写 JSON 里的资源/剧本/画布引用，去掉供应商引用。"""
    asset_keys = {"entity_id", "asset_id", "image_id", "audio_id"}
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if isinstance(v, (dict, list)):
                out[k] = remap(v, amap, smap, pmap)
            elif k in asset_keys and isinstance(v, int):
                out[k] = amap.get(v, 0)
            elif k == "script_id" and isinstance(v, int):
                out[k] = smap.get(v, 0)
            elif k == "project_id" and isinstance(v, int):
                out[k] = pmap.get(v, 0)
            elif k == "provider_id":
                out[k] = None
            elif k in ("asset_ids",) and isinstance(v, list):
                out[k] = [amap.get(x, 0) for x in v if isinstance(x, int)]
            else:
                out[k] = v
        return out
    if isinstance(o, list):
        return [remap(x, amap, smap, pmap) for x in o]
    return o


# --- 1. 用户 ---
demo = U(username=DEMO_USER)
demo.set_password(DEMO_PWD)
demo.first_name = "演示账号"
demo.is_staff = False
demo.is_superuser = False
if COMMIT:
    demo.save()
    prof, _ = Profile.objects.get_or_create(user=demo)
    prof.quota_bytes = QUOTA
    prof.api_calls_remaining = API_CALLS
    prof.save()
    print(f"[1] 用户 {DEMO_USER} 创建，额度 {QUOTA//1024//1024}MB / API 次数 {API_CALLS}")
else:
    print(f"[1] (dry) 将创建用户 {DEMO_USER}")

if not COMMIT:
    print("\n>>> dry run，未写入。确认后加 --commit 执行。")
    sys.exit(0)

demo.refresh_from_db()
MEDIA.mkdir(parents=True, exist_ok=True)

# --- 2. 素材 ---
amap = {}
for a in Asset.objects.filter(user=admin).order_by("id"):
    src = MEDIA / a.path
    if not src.exists():
        print(f"    跳过缺失文件 asset {a.id}: {a.path}")
        continue
    stem = uuid.uuid4().hex
    rel = f"{demo.id}/{stem}{Path(a.path).suffix}"
    (MEDIA / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, MEDIA / rel)
    thumb = ""
    if a.thumbnail and (MEDIA / a.thumbnail).exists():
        trel = f"{demo.id}/{stem}{Path(a.thumbnail).suffix}"
        shutil.copy2(MEDIA / a.thumbnail, MEDIA / trel)
        thumb = trel
    b = Asset.objects.create(
        user=demo, name=a.name, kind=a.kind, path=rel, thumbnail=thumb,
        sha256=a.sha256, size=a.size, metadata=a.metadata, tags=a.tags,
    )
    amap[a.id] = b.id
print(f"[2] 素材克隆 {len(amap)} 条: {amap}")

# --- 3. 剧本 ---
smap = {}
for s in Script.objects.filter(user=admin).order_by("id"):
    n = Script.objects.create(
        user=demo, title=s.title, synopsis=s.synopsis, style=s.style,
        scenes=remap(s.scenes, amap, smap, {}), revision=s.revision,
    )
    smap[s.id] = n.id
print(f"[3] 剧本克隆 {len(smap)} 条: {smap}")

# --- 4. 画布（只要那张成品画布） ---
c = CanvasProject.objects.get(id=11)
nc = CanvasProject.objects.create(
    user=demo, name=c.name, schema_version=c.schema_version,
    revision=c.revision, document=remap(c.document, amap, smap, {}),
)
print(f"[4] 画布克隆 id={nc.id}（原 {c.id}，revision {c.revision}）")

# --- 5. 成片任务 ---
pmap = {c.id: nc.id}
for jid in COPY_JOBS:
    j = Job.objects.get(id=jid)
    result = remap(j.result, amap, smap, pmap)
    src_path = j.result.get("path")
    if src_path and (MEDIA / src_path).exists():
        new_rel = f"outputs/demo-{uuid.uuid4().hex}.mp4"
        shutil.copy2(MEDIA / src_path, MEDIA / new_rel)
        result["path"] = new_rel
        result["size"] = (MEDIA / new_rel).stat().st_size
    nj = Job.objects.create(
        user=demo, kind=j.kind, status=j.status, stage=j.stage, progress=j.progress,
        remote_state={}, snapshot=remap(j.snapshot, amap, smap, pmap), result=result,
        error=j.error, error_code=j.error_code,
        idempotency_key=f"demo-{uuid.uuid4().hex}", attempts=j.attempts,
    )
    Job.objects.filter(id=nj.id).update(
        created_at=j.created_at, started_at=j.started_at, completed_at=j.completed_at)
    for lg in JobLog.objects.filter(job=j):
        nl = JobLog.objects.create(job=nj, message=lg.message)
        JobLog.objects.filter(id=nl.id).update(created_at=lg.created_at)
    print(f"[5] 任务克隆 {jid} -> {nj.id}（{j.stage}，成片 {result.get('size')}B）")

print("\n完成。")
print(json.dumps({
    "user": DEMO_USER,
    "assets": Asset.objects.filter(user=demo).count(),
    "scripts": Script.objects.filter(user=demo).count(),
    "canvases": CanvasProject.objects.filter(user=demo).count(),
    "jobs": Job.objects.filter(user=demo).count(),
    "used_bytes": sum(a.size for a in Asset.objects.filter(user=demo)),
}, ensure_ascii=False))
