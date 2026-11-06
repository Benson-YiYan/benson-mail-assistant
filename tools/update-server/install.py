#!/usr/bin/env python3
"""Install only this service as the current user's login LaunchAgent."""
from pathlib import Path
import os
import plistlib
import shutil
import subprocess
import sys
import time
import server

LABEL = "com.benson.mail-update-server"
home = Path.home()
destination = server.APP
destination.mkdir(parents=True, exist_ok=True)
runtime = destination / "runtime/cloudflared"
if not runtime.is_file():
    existing_runtime = home / "Library/Application Support/DeepSeekHarnessStudent/runtime/0.1.1-rc.2-Darwin-arm64/cloudflared"
    if not existing_runtime.is_file():
        raise SystemExit("Cloudflared runtime is missing; provide BensonMailUpdates/runtime/cloudflared before installing.")
    runtime.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(existing_runtime, runtime)
os.chmod(runtime, 0o755)
shutil.copy2(Path(__file__).with_name("server.py"), destination / "server.py")
logs = home / "Library/Logs/BensonMailUpdates"
logs.mkdir(parents=True, exist_ok=True)
launch_file = home / "Library/LaunchAgents" / (LABEL + ".plist")
launch_file.parent.mkdir(parents=True, exist_ok=True)
configuration = {
    "Label": LABEL,
    "ProgramArguments": [sys.executable, str(destination / "server.py")],
    "RunAtLoad": True,
    "KeepAlive": True,
    "ThrottleInterval": 60,
    "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin", "PYTHONUNBUFFERED": "1"},
    "StandardOutPath": str(logs / "service.log"),
    "StandardErrorPath": str(logs / "service.log"),
    "ProcessType": "Background",
}
with launch_file.open("wb") as stream:
    plistlib.dump(configuration, stream)
os.chmod(launch_file, 0o600)
domain = f"gui/{os.getuid()}"
subprocess.run(["launchctl", "bootout", domain + "/" + LABEL], capture_output=True)
for attempt in range(30):
    started = subprocess.run(["launchctl", "bootstrap", domain, str(launch_file)], capture_output=True)
    if started.returncode == 0:
        break
    # launchd may take a moment to remove the previous job after bootout.
    time.sleep(1)
else:
    raise SystemExit("Could not load this service after 30 seconds; inspect its dedicated LaunchAgent and log.")
print("Installed login service:", LABEL)
