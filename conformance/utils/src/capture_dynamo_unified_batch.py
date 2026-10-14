#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Run the shared legacy Dynamo batch probe against one exact crate release."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from capture_stimulus import batch_final_events, unavailable_result
from impls import BATCH_SOURCE_BLOCKERS, DYNAMO_UNIFIED_PIPELINES


PROBE = Path(__file__).resolve().with_name("legacy_batch_probe.rs")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _probe_job(job: dict) -> dict:
    family = job.get("family")
    if family not in DYNAMO_UNIFIED_PIPELINES:
        raise ValueError(f"no Dynamo v1 batch pipeline registered for family {family!r}")
    reasoning_parser, tool_parser = DYNAMO_UNIFIED_PIPELINES[family]
    return {
        "reasoning_parser": reasoning_parser,
        "tool_parser": tool_parser,
        "job": job,
    }


def _crate_checksum(lock_path: Path, version: str) -> str:
    lock = tomllib.loads(lock_path.read_text())
    matches = [
        package for package in lock["package"]
        if package["name"] == "dynamo-parsers" and package["version"] == version
    ]
    if len(matches) != 1 or matches[0].get("source") != "registry+https://github.com/rust-lang/crates.io-index":
        raise ValueError(f"Cargo.lock does not pin dynamo-parsers {version} from crates.io")
    checksum = matches[0].get("checksum")
    if not isinstance(checksum, str) or len(checksum) != 64:
        raise ValueError(f"Cargo.lock has no registry checksum for dynamo-parsers {version}")
    return checksum


def source_unavailable(version: str, job_path: Path, output_path: Path) -> dict:
    implementation = "dynamo_v1"
    detail = BATCH_SOURCE_BLOCKERS.get((implementation, version))
    if detail is None:
        raise ValueError(f"no explicit source blocker is registered for {implementation} {version}")
    job_bytes = job_path.read_bytes()
    job = json.loads(job_bytes)
    _probe_job(job)
    results = {
        case["id"]: unavailable_result("source_unavailable", detail, capture=case["request"], observation=True)
        for case in job["cases"]
    }
    provenance = {
        "implementation": implementation,
        "version": version,
        "status": "source_unavailable",
        "adapter_sha256": _sha256(PROBE.read_bytes()),
        "job_sha256": _sha256(job_bytes),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        raise FileExistsError(output_path)
    output_path.write_text(json.dumps({"version": version, "results": results, "provenance": provenance}, ensure_ascii=False) + "\n")
    return provenance


def _cargo(cargo: str, args: list[str], *, work_dir: Path, log: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [cargo, *args], cwd=work_dir, env=env, capture_output=True, check=False,
    )
    log.write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"cargo command failed with exit {result.returncode}; see {log}")
    return result


def capture(
    version: str,
    job_path: Path,
    output_path: Path,
    work_dir: Path,
    cargo: str = "cargo",
    target_dir: Path | None = None,
    lockfile: Path | None = None,
) -> dict:
    if not version or any(character not in "0123456789." for character in version):
        raise ValueError(f"invalid Dynamo parser release version: {version!r}")
    if not job_path.is_file():
        raise FileNotFoundError(job_path)
    if not PROBE.is_file():
        raise FileNotFoundError(PROBE)
    work_dir.mkdir(parents=True, exist_ok=True)
    if any(work_dir.iterdir()):
        raise ValueError(f"producer work directory is not empty: {work_dir}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        raise FileExistsError(output_path)

    job_bytes = job_path.read_bytes()
    job = json.loads(job_bytes)
    probe_job_path = work_dir / "probe-job.json"
    probe_job_path.write_text(json.dumps(_probe_job(job), ensure_ascii=False) + "\n")
    (work_dir / "Cargo.toml").write_text(
        "[package]\nname = \"dynamo-unified-batch-probe\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n"
        "[dependencies]\n"
        f"dynamo-parsers = \"={version}\"\n"
        "serde_json = \"1\"\n"
        "tokio = { version = \"1\", features = [\"macros\", \"rt\"] }\n"
    )
    source_dir = work_dir / "src"
    source_dir.mkdir()
    shutil.copyfile(PROBE, source_dir / "main.rs")
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(target_dir or work_dir / "target")
    lock_path = work_dir / "Cargo.lock"
    if lockfile is None:
        _cargo(cargo, ["generate-lockfile", "--manifest-path", str(work_dir / "Cargo.toml")],
               work_dir=work_dir, log=work_dir / "cargo-lock.log", env=env)
    else:
        if not lockfile.is_file():
            raise FileNotFoundError(lockfile)
        lock_path.write_bytes(lockfile.read_bytes())
    crate_checksum = _crate_checksum(lock_path, version)
    result = _cargo(
        cargo,
        ["run", "--locked", "--quiet", "--manifest-path", str(work_dir / "Cargo.toml"), "--", str(probe_job_path)],
        work_dir=work_dir,
        log=work_dir / "cargo-run.log",
        env=env,
    )
    results = json.loads(result.stdout)
    for record in results.values():
        if "batch_final" in record:
            record["assembled"] = batch_final_events(record["batch_final"])
    adapter_sha256 = _sha256(PROBE.read_bytes())
    lock_sha256 = _sha256(lock_path.read_bytes())
    source_sha256 = _sha256(json.dumps({
        "crate_checksum": crate_checksum,
        "cargo_lock_sha256": lock_sha256,
    }, sort_keys=True).encode())
    provenance = {
        "implementation": "dynamo_v1",
        "version": version,
        "source_sha256": source_sha256,
        "adapter_sha256": adapter_sha256,
        "job_sha256": _sha256(job_bytes),
        "crate_checksum": crate_checksum,
        "cargo_lock_sha256": lock_sha256,
    }
    capture_document = {"version": version, "results": results, "provenance": provenance}
    output_path.write_text(json.dumps(capture_document, ensure_ascii=False) + "\n")
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="exact published dynamo-parsers release")
    parser.add_argument("--job", required=True, type=Path, help="family-scoped batch job JSON")
    parser.add_argument("--output", required=True, type=Path, help="capture JSON output; existing files are never overwritten")
    parser.add_argument("--work-dir", required=True, type=Path, help="empty task-owned producer directory for this version")
    parser.add_argument("--cargo", default="cargo", help="Cargo executable")
    parser.add_argument("--target-dir", type=Path, help="version-isolated Cargo build cache")
    parser.add_argument("--lockfile", type=Path, help="reuse a reviewed lockfile for this exact release")
    parser.add_argument("--source-unavailable", action="store_true", help="record a registered source blocker without claiming execution")
    args = parser.parse_args()
    if args.source_unavailable:
        if args.work_dir.exists():
            raise ValueError("source-unavailable records do not create a producer work directory")
        provenance = source_unavailable(args.version, args.job, args.output)
    else:
        provenance = capture(
            args.version,
            args.job,
            args.output,
            args.work_dir,
            args.cargo,
            args.target_dir,
            args.lockfile,
        )
    print(json.dumps({"version": args.version, "provenance": provenance}, sort_keys=True))


if __name__ == "__main__":
    main()
