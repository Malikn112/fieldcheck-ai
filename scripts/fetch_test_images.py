#!/usr/bin/env python3
"""
Seed script — downloads 3 real sample industrial asset photos into
`/test_assets` for use by the demo pipeline and manual testing.

Sources are public-domain / freely-licensed images from Wikimedia Commons.
If network access is unavailable (offline dev environment, CI sandbox),
the script falls back to generating simple synthetic placeholder images
with Pillow so the rest of the pipeline (upload -> mock vision -> report)
remains fully runnable without internet access.

Usage:
    python scripts/fetch_test_images.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
TEST_ASSETS_DIR = ROOT / "test_assets"

# Public-domain / CC-licensed images of the three target asset categories.
IMAGES = [
    {
        "filename": "pressure_gauge.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6c/Manometer3.jpg/640px-Manometer3.jpg",
        "label": "Pressure Gauge",
    },
    {
        "filename": "control_valve.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Valve_pneumatic_actuator.jpg/640px-Valve_pneumatic_actuator.jpg",
        "label": "Control Valve",
    },
    {
        "filename": "electrical_panel.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/97/Electrical_panel.jpg/640px-Electrical_panel.jpg",
        "label": "Electrical Panel",
    },
]


def _make_placeholder(path: Path, label: str) -> None:
    """Generate a simple synthetic JPEG so the demo can run fully offline."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 480), color=(60, 70, 90))
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, 600, 440], outline=(200, 200, 200), width=4)
    draw.ellipse([220, 140, 420, 340], outline=(220, 220, 220), width=6)
    text = f"[PLACEHOLDER]\n{label}"
    draw.text((60, 400), text, fill=(255, 255, 255))
    img.save(path, format="JPEG", quality=88)


def fetch_all(force: bool = False) -> list[Path]:
    TEST_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        for item in IMAGES:
            dest = TEST_ASSETS_DIR / item["filename"]
            if dest.exists() and not force:
                print(f"  [skip] {dest.name} already exists")
                saved.append(dest)
                continue

            try:
                print(f"  [download] {item['label']} <- {item['url']}")
                resp = client.get(item["url"])
                resp.raise_for_status()
                dest.write_bytes(resp.content)
                print(f"    saved -> {dest} ({len(resp.content) / 1024:.0f} KB)")
            except Exception as exc:  # noqa: BLE001
                print(f"    [warn] download failed ({exc}); generating placeholder instead.")
                _make_placeholder(dest, item["label"])
                print(f"    saved placeholder -> {dest}")

            saved.append(dest)

    return saved


if __name__ == "__main__":
    force = "--force" in sys.argv
    print(f"Seeding test images into: {TEST_ASSETS_DIR}")
    paths = fetch_all(force=force)
    print(f"\nDone. {len(paths)} image(s) available:")
    for p in paths:
        print(f"  - {p}")
