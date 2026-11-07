#!/usr/bin/env python3
import json, time, os
from pathlib import Path

target = Path("/opt/storyframe-studio/metrics/host-metrics.json")
target.parent.mkdir(exist_ok=True)
while True:
    values = {
        line.split(":")[0]: line.split(":")[1].strip()
        for line in Path("/proc/meminfo").read_text().splitlines()
    }
    tmp = target.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "timestamp": time.time(),
                "available_mb": int(values["MemAvailable"].split()[0]) / 1024,
            }
        )
    )
    os.replace(tmp, target)
    time.sleep(2)
