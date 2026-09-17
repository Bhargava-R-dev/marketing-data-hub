"""Exercise the packaged GUI -> CLI sync path without accounts or browser tabs.

Run on Windows after PyInstaller: python packaging/smoke_test.py <bundle-dir>
"""
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def request(url, token=None, method="GET"):
    headers = {"X-Setup-Token": token} if token else {}
    req = urllib.request.Request(url, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=3) as response:
        return response.read().decode()


def main(bundle):
    gui = bundle / "MarketingDataHub.exe"
    cli = bundle / "hub.exe"
    subprocess.run([str(cli), "--version"], check=True, timeout=30)
    with tempfile.TemporaryDirectory(prefix="hub smoke ") as folder:
        home = Path(folder)
        cfg = home / "config.yaml"
        cfg.write_text("db_path: data/hub.duckdb\nsecrets_dir: secrets\n"
                       "exports_dir: exports\nconnectors: {}\n", encoding="utf-8")
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        proc = subprocess.Popen([str(gui), "setup", "--no-browser", "--port", str(port),
                                 "--config", str(cfg)])
        token = None
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise AssertionError(f"GUI exited early: {proc.returncode}")
                try:
                    page = request(url)
                    token = re.search(r'const TOKEN = "([^"]+)"', page).group(1)
                    break
                except (OSError, TimeoutError):
                    time.sleep(.2)
            assert token, "GUI never became ready"
            second = subprocess.run([str(gui), "setup", "--no-browser", "--port", str(port),
                                      "--config", str(cfg)], timeout=30)
            assert second.returncode != 0, "Port collision was silently accepted"
            result = json.loads(request(url + "/api/sync", token, "POST"))
            assert result["status"] == "started", result
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                result = json.loads(request(url + "/api/sync/status", token))
                if not result["in_progress"]:
                    break
                time.sleep(.2)
            assert not result["in_progress"], "Sync never finished"
            assert not result.get("error"), result
            assert result["run"]["finished_at"], result
            assert (home / "data/hub.duckdb").exists()
            subprocess.run([str(gui), "sync", "all", "--unattended", "--config", str(cfg)],
                           check=True, timeout=60)
        finally:
            if token and proc.poll() is None:
                try:
                    request(url + "/api/shutdown", token, "POST")
                    proc.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    proc.terminate()
            elif proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=10)
    print("PASS: packaged GUI startup, port conflict, background sync, argument forwarding, shutdown")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
