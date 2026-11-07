"""Run against the isolated deployed studio. Uses only local fixture media; no AI calls."""

import io, json, os, time, wave, math, struct, uuid, subprocess
from pathlib import Path
import httpx
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
report = {
    "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "benchmarks": [],
    "checks": [],
}
password = next(
    s.split("=", 1)[1]
    for s in (ROOT / ".env").read_text().splitlines()
    if s.startswith("ADMIN_PASSWORD=")
)
c = httpx.Client(base_url="http://127.0.0.1:8010", timeout=30)


def request(method, path, body=None, files=None):
    if method != "GET":
        token = c.get("/api/csrf/").json()["csrfToken"]
    else:
        token = ""
    r = c.request(
        method,
        "/api/" + path,
        json=body if not files else None,
        files=files,
        headers={"X-CSRFToken": token},
    )
    if not r.is_success:
        raise RuntimeError(f"{method} {path}: {r.status_code} {r.text[:500]}")
    return r.json() if r.status_code != 204 else None


for attempt in range(60):
    try:
        if c.get("/health/").is_success:
            break
    except httpx.HTTPError:
        pass
    time.sleep(1)
request("POST", "auth/login/", {"username": "admin", "password": password})
images = []
for i in range(2):
    im = Image.new("RGB", (1024, 576))
    draw = ImageDraw.Draw(im)
    for y in range(576):
        draw.line((0, y, 1024, y), fill=(120 + i * 30, int(160 - y / 12), 140 + i * 20))
    draw.ellipse((650, 80, 800, 230), fill=(240, 224, 175))
    draw.polygon([(0, 500), (330, 200), (720, 576)], fill=(65, 104, 90))
    draw.polygon(
        [(380, 576), (780, 280), (1024, 480), (1024, 576)], fill=(86, 121, 103)
    )
    blob = io.BytesIO()
    im.save(blob, "PNG")
    images.append(
        request(
            "POST",
            "assets/",
            files={
                "file": (
                    f"verification-landscape-{i}.png",
                    blob.getvalue(),
                    "image/png",
                )
            },
        )["id"]
    )
audio = io.BytesIO()
with wave.open(audio, "wb") as f:
    f.setnchannels(1)
    f.setsampwidth(2)
    f.setframerate(22050)
    f.writeframes(
        b"".join(
            struct.pack("<h", int(1500 * math.sin(2 * math.pi * 440 * t / 22050)))
            for t in range(22050 * 3)
        )
    )
audio_id = request(
    "POST",
    "assets/",
    files={"file": ("verification-tone.wav", audio.getvalue(), "audio/wav")},
)["id"]


def scenes(duration):
    return [
        {
            "description": "测试用图片素材：山间与日光",
            "dialogue": f"第{i+1}个镜头：让故事在光影中慢慢展开。",
            "duration": 5,
            "image_id": images[i % 2],
            "audio_id": audio_id,
        }
        for i in range(duration // 5)
    ]


def make_script(duration):
    return request(
        "POST",
        "scripts/",
        {
            "title": f"验收 · {duration}秒山间来信",
            "synopsis": "使用测试图片与提示音验证合成，无真实AI调用。",
            "style": "甜宠",
            "scenes": scenes(duration),
        },
    )


def wait_job(job, cancel=False):
    start = time.monotonic()
    minimum = 100000
    health_ok = True
    while time.monotonic() - start < 300:
        result = request("GET", f'jobs/{job["id"]}/')
        metrics = json.loads((ROOT / "metrics/host-metrics.json").read_text())
        minimum = min(minimum, metrics["available_mb"])
        try:
            health_ok = (
                health_ok
                and httpx.get("http://127.0.0.1:3000/health", timeout=3).is_success
            )
        except Exception:
            health_ok = False
        if result["status"] not in ["queued", "running", "cancel_requested"]:
            return result, time.monotonic() - start, minimum, health_ok
        if cancel and result["status"] == "running":
            request("POST", f'jobs/{job["id"]}/cancel/', {})
        time.sleep(1)
    raise RuntimeError("验收等待超时")


def peak():
    return int(
        subprocess.check_output(
            [
                "sudo",
                "-n",
                "docker",
                "compose",
                "exec",
                "-T",
                "worker",
                "cat",
                "/sys/fs/cgroup/memory.peak",
            ],
            cwd=ROOT,
        ).decode()
    )


for duration in [15, 60]:
    script = make_script(duration)
    job = request(
        "POST",
        "jobs/",
        {
            "kind": "compose",
            "script_id": script["id"],
            "use_tts": False,
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    result, elapsed, minimum, health_ok = wait_job(job)
    assert result["status"] == "succeeded", result
    assert health_ok and minimum >= 200
    response = c.get(result["download_url"])
    assert response.is_success and len(response.content) > 1000
    report["benchmarks"].append(
        {
            "duration": duration,
            "wall_seconds": round(elapsed, 2),
            "host_min_available_mb": round(minimum, 2),
            "worker_container_peak_bytes": peak(),
            "output_bytes": len(response.content),
            "taskflow_healthy": health_ok,
            "job_id": job["id"],
        }
    )
script = make_script(60)
job = request(
    "POST",
    "jobs/",
    {
        "kind": "compose",
        "script_id": script["id"],
        "idempotency_key": str(uuid.uuid4()),
    },
)
result, *_ = wait_job(job, cancel=True)
assert result["status"] == "cancelled", result
report["checks"].append("Running task cancellation reached cancelled")
script = make_script(15)
doc = {
    "nodes": [
        {
            "id": "script",
            "type": "studio",
            "position": {"x": 30, "y": 100},
            "data": {
                "kind": "script",
                "label": "山间来信 · 剧本",
                "entity_id": script["id"],
            },
        },
        {
            "id": "compose",
            "type": "studio",
            "position": {"x": 350, "y": 100},
            "data": {"kind": "compose", "label": "合成 720p"},
        },
        {
            "id": "result",
            "type": "studio",
            "position": {"x": 670, "y": 100},
            "data": {"kind": "result", "label": "成片预览"},
        },
    ],
    "edges": [
        {"id": "e1", "source": "script", "target": "compose"},
        {"id": "e2", "source": "compose", "target": "result"},
    ],
    "viewport": {"x": 0, "y": 0, "zoom": 1},
}
canvas = request("POST", "canvases/", {"name": "山间来信 · 创作流程"})
canvas = request(
    "PUT",
    f'canvases/{canvas["id"]}/',
    {"name": canvas["name"], "revision": canvas["revision"], "document": doc},
)
job = request(
    "POST",
    f'canvases/{canvas["id"]}/run/',
    {"revision": canvas["revision"], "idempotency_key": str(uuid.uuid4())},
)
result, *_ = wait_job(job)
assert result["status"] == "succeeded", result
report["checks"].append("Canvas script -> compose -> result completed")
report["canvas_id"] = canvas["id"]
report["canvas_job_id"] = job["id"]
report["script_id"] = script["id"]
report["asset_ids"] = images + [audio_id]
report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs/integration-results.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2)
)
print(json.dumps(report, ensure_ascii=False, indent=2))
