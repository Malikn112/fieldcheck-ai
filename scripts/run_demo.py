#!/usr/bin/env python3
"""
Automated end-to-end demo pipeline for FieldCheck AI.

What it does:
  1. Ensures 3 sample industrial images exist in /test_assets (downloads or
     generates placeholders via fetch_test_images.py).
  2. Starts the FastAPI backend (uvicorn) as a subprocess, if not already
     running at the configured host/port.
  3. Simulates 3 field-inspector uploads via real HTTP calls to the API.
  4. Polls each inspection until COMPLETED (or FAILED), printing formatted
     terminal output of the extracted structured JSON.
  5. Saves the generated HTML report for each inspection into
     /output_reports.

Usage:
    python scripts/run_demo.py
    python scripts/run_demo.py --host 127.0.0.1 --port 8000
    python scripts/run_demo.py --no-server   # assume server already running
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_test_images import fetch_all, TEST_ASSETS_DIR  # noqa: E402

OUTPUT_REPORTS_DIR = ROOT / "output_reports"


def _wait_for_server(base_url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    with httpx.Client(timeout=3.0) as client:
        while time.time() < deadline:
            try:
                res = client.get(f"{base_url}/health")
                if res.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(1.0)
    return False


def _start_server(host: str, port: int) -> tuple[subprocess.Popen, Path]:
    """Launch uvicorn as a subprocess, with its stdout/stderr redirected to
    a log file rather than an undrained `subprocess.PIPE`.

    IMPORTANT: `subprocess.PIPE` has a small OS-level buffer (~64KB on
    Linux). If nobody actively reads it, and the child process logs more
    than that (e.g. SQLAlchemy's verbose `echo=True` debug logging in dev
    mode), the child's `write()` to stdout blocks once the pipe fills —
    which freezes the *entire* uvicorn event loop, silently hanging every
    in-flight and future request. Logging to a file sidesteps this
    entirely.
    """
    log_path = ROOT / "output_reports" / "_demo_server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Starting FastAPI server at {host}:{port} ... (log: {log_path})")

    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port)],
        cwd=str(ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    return proc, log_path


def _print_banner(text: str) -> None:
    print("\n" + "=" * 78)
    print(text)
    print("=" * 78)


def _print_json_block(title: str, data: dict) -> None:
    print(f"\n--- {title} ---")
    print(json.dumps(data, indent=2, default=str))


def simulate_upload(client: httpx.Client, base_url: str, image_path: Path, inspector: str, site: str) -> str:
    with open(image_path, "rb") as f:
        files = {"file": (image_path.name, f, "image/jpeg" if image_path.suffix != ".png" else "image/png")}
        data = {"inspector_name": inspector, "site_location": site}
        res = client.post(f"{base_url}/api/v1/inspections/upload", files=files, data=data)
    res.raise_for_status()
    body = res.json()
    print(f"  Uploaded {image_path.name} -> inspection_id={body['inspection_id']} status={body['status']}")
    return body["inspection_id"]


def poll_until_done(client: httpx.Client, base_url: str, inspection_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    last_status = None
    while time.time() < deadline:
        res = client.get(f"{base_url}/api/v1/inspections/{inspection_id}")
        res.raise_for_status()
        data = res.json()
        if data["status"] != last_status:
            print(f"  [{inspection_id[:8]}] status -> {data['status']}")
            last_status = data["status"]
        if data["status"] in ("COMPLETED", "FAILED"):
            return data
        time.sleep(1.5)
    raise TimeoutError(f"Inspection {inspection_id} did not finish within {timeout}s")


def save_report(client: httpx.Client, base_url: str, inspection_id: str) -> Path:
    res = client.get(f"{base_url}/api/v1/inspections/{inspection_id}/report")
    res.raise_for_status()
    OUTPUT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_REPORTS_DIR / f"inspection_{inspection_id}.html"
    out_path.write_text(res.text, encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="FieldCheck AI end-to-end demo runner")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-server", action="store_true", help="Assume the API server is already running.")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    _print_banner("STEP 1/4 — Ensuring sample industrial images exist")
    images = fetch_all()
    if len(images) < 3:
        print("ERROR: fewer than 3 test images available.", file=sys.stderr)
        return 1

    server_proc = None
    server_log_path = None
    try:
        if not args.no_server:
            _print_banner("STEP 2/4 — Starting backend service")
            server_proc, server_log_path = _start_server(args.host, args.port)
            if not _wait_for_server(base_url):
                print("ERROR: server did not become healthy in time.", file=sys.stderr)
                if server_log_path and server_log_path.exists():
                    print(server_log_path.read_text()[-4000:])
                return 1
            print("Server is healthy.")
        else:
            _print_banner("STEP 2/4 — Using already-running backend service")
            if not _wait_for_server(base_url, timeout=5):
                print(f"ERROR: no server responding at {base_url}", file=sys.stderr)
                return 1

        _print_banner("STEP 3/4 — Simulating 3 field-inspector uploads")
        inspectors = [
            ("Alex Rivera", "Plant 1 - Boiler Room"),
            ("Priya Nair", "Plant 2 - Compressor Station"),
            ("Sam Okafor", "Plant 3 - Substation B"),
        ]

        results = []
        with httpx.Client(timeout=30.0) as client:
            inspection_ids = []
            for image_path, (inspector, site) in zip(images[:3], inspectors):
                inspection_id = simulate_upload(client, base_url, image_path, inspector, site)
                inspection_ids.append((inspection_id, image_path.name))

            _print_banner("STEP 4/4 — Waiting for AI analysis to complete")
            for inspection_id, filename in inspection_ids:
                data = poll_until_done(client, base_url, inspection_id)
                _print_json_block(f"RESULT: {filename} (inspection_id={inspection_id})", data)
                results.append(data)

                if data["status"] == "COMPLETED":
                    report_path = save_report(client, base_url, inspection_id)
                    print(f"  Report saved -> {report_path}")

        _print_banner("DEMO SUMMARY")
        for data in results:
            asset_type = (data.get("asset") or {}).get("asset_type", "Unknown")
            condition = data.get("overall_condition", "N/A")
            defect_count = len(data.get("defects", []))
            print(f"  {data['original_filename']:<25} | {asset_type:<18} | {condition:<12} | {defect_count} defect(s)")

        completed = sum(1 for d in results if d["status"] == "COMPLETED")
        print(f"\n{completed}/{len(results)} inspections completed successfully.")
        print(f"HTML reports written to: {OUTPUT_REPORTS_DIR}")
        return 0 if completed == len(results) else 2

    finally:
        if server_proc is not None:
            print("\nShutting down demo server...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
