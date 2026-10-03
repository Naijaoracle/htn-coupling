#!/usr/bin/env python3
"""Import selected sensor acquisition records and synchronization analyses."""
from __future__ import annotations

import hashlib
import argparse
import json
import re
from pathlib import Path


SELECTIONS = {
    "esp32_max30102": [
        "extract_ipad_overlap.py",
        "max30102_collect.py",
        "max30102_smoke.csv",
        "run_marked_audio_ppg.py",
        "take_01.csv",
        "take_01_analysis.md",
        "take_02_soldered.csv",
        "take_02_soldered_analysis.md",
        "take_03_h10_sync.csv",
        "take_03_h10_sync_analysis.md",
        "take_04_three_modality_analysis.md",
        "take_04_three_modality_contact.csv",
    ],
    "synchronized_capture_analysis": [
        "synchronized_capture_analysis.json",
        "synchronized_capture_analysis.md",
        "synchronized_capture_analysis_final.md",
        "take1_stability_gate.json",
        "take2_stability_gate.json",
    ],
}
PATH_RE = re.compile(r"(?<![A-Za-z0-9])/(?:home|tmp|mnt|media)/[^\s\"'<>]+")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Local research archive directory")
    parser.add_argument("--destination", type=Path, required=True, help="Research-record destination directory")
    args = parser.parse_args()
    source_root = args.source.expanduser().resolve()
    destination_root = args.destination.expanduser().resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    copied = []
    missing = []
    for folder, names in SELECTIONS.items():
        for name in names:
            source = source_root / folder / name
            if not source.is_file():
                missing.append(f"{folder}/{name}")
                continue
            raw = source.read_bytes()
            if source.suffix.lower() in {".py", ".md", ".json"}:
                text = raw.decode("utf-8", errors="replace")
                text = PATH_RE.sub("[local path omitted]", text)
                raw = text.encode("utf-8")
            target = destination_root / folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            copied.append({
                "record": f"{folder}/{name}",
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
    (destination_root / "transfer_manifest.json").write_text(json.dumps({
        "schema": "acquisition_records_transfer_v1",
        "source_archive_id": "local_research_archive",
        "copied": copied,
        "not_found": missing,
        "raw_audio_video_copied": False,
        "local_paths_removed_from_text": True,
    }, indent=2) + "\n", encoding="utf-8")
    (destination_root / "README.md").write_text(
        "# Acquisition and synchronization records\n\n"
        "Selected MAX30102/ESP32 acquisition records, analysis notes, extraction scripts and timing analyses. "
        "Raw audio and video are not included. This directory is part of the research record and is not the public demo bundle.\n",
        encoding="utf-8",
    )
    print(json.dumps({"copied": len(copied), "not_found": missing}, indent=2))


if __name__ == "__main__":
    main()
