# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import sys
from pathlib import Path
from subprocess import CompletedProcess

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import capture_dynamo_unified_batch as capture  # noqa: E402


def test_probe_job_uses_registered_gpt_oss_pipeline_without_changing_request() -> None:
    job = {"family": "gpt_oss", "cases": [{"id": "UNIFIED.example.gpt_oss", "request": {"input": "authored"}}]}

    wrapped = capture._probe_job(job)

    assert wrapped["reasoning_parser"] == "gpt_oss"
    assert wrapped["tool_parser"] == "harmony"
    assert wrapped["job"] is job


def test_probe_job_rejects_unregistered_family() -> None:
    with pytest.raises(ValueError, match="no Dynamo v1 batch pipeline"):
        capture._probe_job({"family": "unknown", "cases": []})


def test_crate_checksum_requires_exact_registry_package(tmp_path: Path) -> None:
    lock = tmp_path / "Cargo.lock"
    lock.write_text(
        'version = 3\n\n[[package]]\nname = "dynamo-parsers"\nversion = "10.0.1"\n'
        'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
        f'checksum = "{"a" * 64}"\n'
    )

    assert capture._crate_checksum(lock, "10.0.1") == "a" * 64
    with pytest.raises(ValueError, match="does not pin"):
        capture._crate_checksum(lock, "9.2.13")


def test_registered_source_blocker_binds_every_unattempted_request(tmp_path: Path) -> None:
    job_path = tmp_path / "job.json"
    output_path = tmp_path / "capture.json"
    request = {
        "input": "authored",
        "init": {"starting_state": "None", "tool_output_mode": "Native", "named_tool": None},
        "finish_reason": "stop",
        "tools": [],
        "chunks": [{"delta_text": "authored"}],
    }
    job = {"family": "gpt_oss", "cases": [{"id": "UNIFIED.example.gpt_oss", "request": request}]}
    job_path.write_text(json.dumps(job))

    provenance = capture.source_unavailable("9.2.13", job_path, output_path)
    result = json.loads(output_path.read_text())

    assert provenance["status"] == "source_unavailable"
    assert "source_sha256" not in provenance
    assert result["results"]["UNIFIED.example.gpt_oss"]["capture_input"] == request
    assert result["results"]["UNIFIED.example.gpt_oss"]["capture_observation"]["unavailable"]["code"] == "source_unavailable"


def test_capture_uses_the_requested_version_isolated_target_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    job_path = tmp_path / "job.json"
    output_path = tmp_path / "capture.json"
    work_dir = tmp_path / "producer"
    target_dir = tmp_path / "target-10.0.1"
    request = {
        "input": "authored",
        "init": {"starting_state": "None", "tool_output_mode": "Native", "named_tool": None},
        "finish_reason": "stop",
        "tools": [],
        "chunks": [{"delta_text": "authored"}],
    }
    job = {"family": "gpt_oss", "cases": [{"id": "case", "request": request}]}
    job_path.write_text(json.dumps(job))
    calls = []

    def fake_run(args, *, cwd, env, capture_output, check):
        calls.append((args, cwd, env["CARGO_TARGET_DIR"]))
        if "generate-lockfile" in args:
            (cwd / "Cargo.lock").write_text(
                'version = 3\n\n[[package]]\nname = "dynamo-parsers"\nversion = "10.0.1"\n'
                'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
                f'checksum = "{"a" * 64}"\n'
            )
            return CompletedProcess(args, 0, b"", b"")
        return CompletedProcess(
            args,
            0,
            json.dumps({
                "case": {
                    "batch_final": {"reasoning_text": "", "normal_text": "authored", "calls": []},
                    "capture_input": request,
                }
            }).encode(),
            b"",
        )

    monkeypatch.setattr(capture.subprocess, "run", fake_run)
    monkeypatch.setattr(capture, "PROBE", tmp_path / "legacy_batch_probe.rs")
    capture.PROBE.write_text("probe")

    receipt = capture.capture("10.0.1", job_path, output_path, work_dir, target_dir=target_dir)

    assert [call[2] for call in calls] == [str(target_dir), str(target_dir)]
    assert receipt["job_sha256"] == capture._sha256(job_path.read_bytes())
    result = json.loads(output_path.read_text())["results"]["case"]
    assert result["capture_input"] == request
    assert result["assembled"] == [{"kind": "text", "text": "authored"}]
