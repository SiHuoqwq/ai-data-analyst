import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ALIAS = next(
    (
        candidate
        for candidate in PROJECT_ROOT.parent.iterdir()
        if candidate != PROJECT_ROOT
        and candidate.is_dir()
        and candidate.resolve() == PROJECT_ROOT
    ),
    PROJECT_ROOT,
)
POWERSHELL = shutil.which("powershell")


def _run_start_script(*arguments: str, environment: dict[str, str]):
    if not POWERSHELL:
        pytest.skip("Windows PowerShell is not available")
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROJECT_ROOT / "start-demo.ps1"),
            *arguments,
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_demo_start_check_defaults_to_fake_and_frontend_5174():
    environment = os.environ.copy()
    environment["V2_PROVIDER"] = "deepseek"
    environment.pop("DEEPSEEK_API_KEY", None)

    result = _run_start_script("-CheckOnly", environment=environment)

    assert result.returncode == 0, result.stderr
    assert "Provider: Fake" in result.stdout
    assert "http://localhost:5174" in result.stdout
    assert "deepseek_api_key" not in result.stdout.lower()


def test_demo_start_refuses_deepseek_without_key_and_never_prints_a_key():
    environment = os.environ.copy()
    environment.pop("DEEPSEEK_API_KEY", None)

    result = _run_start_script(
        "-Provider",
        "DeepSeek",
        "-CheckOnly",
        environment=environment,
    )

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "DEEPSEEK_API_KEY" in combined
    assert "sk-" not in combined


def test_demo_stop_accepts_equivalent_junction_project_path(tmp_path):
    if not POWERSHELL:
        pytest.skip("Windows PowerShell is not available")

    runtime_root = tmp_path / "xishu-demo-runtime"
    runtime_root.mkdir()
    (runtime_root / "processes.json").write_text(
        json.dumps(
            {
                "project_root": str(PROJECT_ROOT),
                "backend_pid": 2147483001,
                "frontend_pid": 2147483002,
            }
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["TEMP"] = str(tmp_path)
    environment["TMP"] = str(tmp_path)

    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROJECT_ALIAS / "stop-demo.ps1"),
        ],
        cwd=PROJECT_ALIAS,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not (runtime_root / "processes.json").exists()
