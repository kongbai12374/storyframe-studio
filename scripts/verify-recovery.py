import json, time, uuid, subprocess
from pathlib import Path
import httpx

root = Path(__file__).resolve().parent.parent
password = next(
    s.split("=", 1)[1]
    for s in (root / ".env").read_text().splitlines()
    if s.startswith("ADMIN_PASSWORD=")
)
c = httpx.Client(base_url="http://127.0.0.1:8010", timeout=20)


def call(method, path, data=None):
    token = c.get("/api/csrf/").json()["csrfToken"] if method != "GET" else ""
    r = c.request(method, "/api/" + path, json=data, headers={"X-CSRFToken": token})
    r.raise_for_status()
    return r.json()


call("POST", "auth/login/", {"username": "admin", "password": password})
script = next(
    s
    for s in call("GET", "scripts/?limit=100")["results"]
    if sum(x["duration"] for x in s["scenes"]) == 60
)
job = call(
    "POST",
    "jobs/",
    {
        "kind": "compose",
        "script_id": script["id"],
        "idempotency_key": str(uuid.uuid4()),
    },
)
for _ in range(30):
    state = call("GET", f'jobs/{job["id"]}/')
    if state["status"] == "running":
        break
    time.sleep(1)
else:
    raise RuntimeError("Worker did not start the recovery fixture")
subprocess.run(
    ["sudo", "-n", "docker", "compose", "kill", "-s", "SIGKILL", "worker"],
    cwd=root,
    check=True,
)
subprocess.run(
    ["sudo", "-n", "docker", "compose", "up", "-d", "--no-build", "worker"],
    cwd=root,
    check=True,
)
for _ in range(40):
    state = call("GET", f'jobs/{job["id"]}/')
    if state["status"] == "interrupted":
        break
    time.sleep(1)
assert state["status"] == "interrupted", state
assert not any((root / "runtime/media/tmp" / str(job["id"])).glob("*"))
report = {
    "worker_kill_recovery": "passed",
    "job_id": job["id"],
    "status": state["status"],
    "temporary_files_cleaned": True,
    "automatic_paid_retry": False,
}
(root / "docs/recovery-results.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
