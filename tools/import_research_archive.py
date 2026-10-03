#!/usr/bin/env python3
"""Copy the reproducible, non-sensitive part of the optical research archive.

Large MCX detector histories, raw capture media, credentials, and caches remain
outside this repository. A manifest records copied-file hashes and exclusion
counts without embedding local source paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path


TEXT_EXTENSIONS = {".md", ".py", ".json", ".csv", ".yaml", ".yml", ".txt", ".tex", ".bib"}
SAFE_EXTENSIONS = TEXT_EXTENSIONS | {".png", ".pdf", ".raw"}
ROOT_FILES = {
    "COMPARISON_BLIND_GATE_CRITERIA.md",
    "CONTACT_REFLECTANCE_ENGINEERING_GATE_REPORT.md",
    "MCX_ENGINEERING_PILOT_REPORT.md",
    "final_comparative_lock.json",
    "pilot_manifest.json",
    "lapitan_generic_phantom_coefficients_candidate.csv",
}
EXCLUDED_DIRS = {
    "ipad_rppg_private", "device_characterization", "__pycache__",
    ".git", ".venv", "node_modules",
}
EXCLUDED_NAMES = {
    "CAMERA_TRANSLATION_ENGINEERING_PLAN.md",
    "camera_engineering_config_draft.json",
}
ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9])/(?:home|tmp|mnt|media)/[^\s\"'<>]+")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def include_file(relative: Path) -> tuple[bool, str]:
    parts = relative.parts
    name = relative.name
    suffix = relative.suffix.lower()
    if any(part in EXCLUDED_DIRS for part in parts):
        return False, "private_or_cache_tree"
    if suffix in {".key", ".crt", ".pem", ".p12", ".pfx", ".env", ".mch", ".mc2", ".wav", ".avi", ".yuyv", ".npy", ".npz", ".pyc", ".log", ".jsonl"}:
        return False, "credential_media_or_large_run_output"
    if name in EXCLUDED_NAMES or "ENGINEERING_PLAN" in name or "STRATEGY" in name:
        return False, "planning_or_draft"
    if suffix == ".raw" and parts[0] != "inputs":
        return False, "generated_raw_fixture"
    if suffix not in SAFE_EXTENSIONS:
        return False, "unsupported_or_build_artifact"
    if len(parts) == 1:
        return name in ROOT_FILES, "selected_root_record" if name in ROOT_FILES else "not_selected"
    if parts[0] == "runs":
        return name == "config.json", "run_configuration" if name == "config.json" else "large_run_output"
    return True, "reproducible_record"


def sanitize(data: bytes, suffix: str) -> bytes:
    if suffix.lower() not in TEXT_EXTENSIONS:
        return data
    text = data.decode("utf-8", errors="replace")
    text = ABSOLUTE_PATH_RE.sub("[local path omitted]", text)
    return text.encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Source optical_bootstrap_pilot archive directory")
    parser.add_argument("--destination", type=Path, required=True, help="Research-record destination directory")
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    destination = args.destination.resolve()
    if not source.is_dir():
        raise SystemExit(f"Source directory does not exist: {source}")
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"Destination is not empty; refusing to overwrite: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    copied: list[dict[str, object]] = []
    excluded: Counter[str] = Counter()
    excluded_bytes: Counter[str] = Counter()
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(source)
        selected, category = include_file(relative)
        if not selected:
            excluded[category] += 1
            excluded_bytes[category] += path.stat().st_size
            continue
        raw = path.read_bytes()
        output = sanitize(raw, path.suffix)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(output)
        copied.append({
            "path": relative.as_posix(),
            "bytes": len(output),
            "sha256": sha256(output),
        })

    readme = """# Optical bootstrap research record\n\nThis is the reproducible, compact research record transferred from the local optical-bootstrap archive. It includes protocols, code, MCX configurations, compact summaries, and selected waveform tables. It excludes raw participant camera/audio captures, credentials, caches, MCX detector-history binaries, and transient logs. The excluded detector histories were large generated outputs; their configurations and compact analysis products are retained where available.\n\nThis directory is the scientific record, not the public website bundle. Public-facing data are generated separately through an allow-listed export and must not be made by copying this directory wholesale.\n\nThe optical results are conditional model results. The contact-reflectance model uses assumed upstream-vessel-to-dermis transfer parameters and a generic tissue phantom; it is not a validated facial rPPG model. Visible-camera controls and RGB/POS/CHROM engineering gates have their own documented scope and must not be conflated with contact-reflectance route results.\n"""
    (destination / "README.md").write_text(readme, encoding="utf-8")
    manifest = {
        "schema": "research_archive_transfer_v1",
        "source_archive_id": "local_research_archive/optical_bootstrap_pilot",
        "destination_id": "htn-coupling/research_records/optical_bootstrap_pilot",
        "source_file_count": sum(1 for p in source.rglob("*") if p.is_file() and not p.is_symlink()),
        "copied_file_count": len(copied),
        "copied_bytes": sum(int(item["bytes"]) for item in copied),
        "excluded_file_count": sum(excluded.values()),
        "excluded_bytes": sum(excluded_bytes.values()),
        "excluded_by_category": {
            key: {"files": excluded[key], "bytes": excluded_bytes[key]}
            for key in sorted(excluded)
        },
        "copied_files": copied,
        "local_paths_removed_from_text": True,
        "raw_participant_media_copied": False,
        "credentials_copied": False,
        "mcx_detector_histories_copied": False,
    }
    (destination / "transfer_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "copied_files"}, indent=2))


if __name__ == "__main__":
    main()
