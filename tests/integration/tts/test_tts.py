"""Tests for tts.py fallback behavior."""

import json
import subprocess
import sys
from pathlib import Path


SCRIPTS_PATH = (
    Path(__file__).parent.parent.parent.parent / "skills" / "x-news-tts" / "scripts"
)
sys.path.insert(0, str(SCRIPTS_PATH))

import tts


def test_main_falls_back_to_edge_tts_cli(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "script.txt"
    output_path = tmp_path / "audio.mp3"
    log_path = tmp_path / "runtime" / "daily" / "2026-04-02" / "run.log.jsonl"
    input_path.write_text("你好，世界", encoding="utf-8")
    monkeypatch.setenv("RUN_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("REPORT_DATE", "2026-04-02")
    monkeypatch.setenv("RUN_ID", "test-run")
    monkeypatch.setenv("RUN_LOG_PATH", str(log_path))

    def fake_import_module(name):
        raise ModuleNotFoundError(name)

    def fake_run(cmd, capture_output, text):
        output_path.write_bytes(b"mp3")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(tts.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(tts.subprocess, "run", fake_run)

    tts.main(["--input", str(input_path), "--output", str(output_path)])

    captured = capsys.readouterr()
    assert output_path.exists()
    assert "falling back to edge-tts CLI" in captured.err
    assert f"Saved: {output_path}" in captured.out
    events = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [event["event"] for event in events] == [
        "step_start",
        "step_warning",
        "write_output",
        "step_complete",
    ]


def test_help_works_via_cli() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_PATH / "tts.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Speech rate (default: +0%)" in result.stdout
