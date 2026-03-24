from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from specflow.cli.main import app

runner = CliRunner()


def test_cli_debug_run_status_and_artifacts(tmp_path: Path) -> None:
    env = _cli_env(tmp_path)

    started = runner.invoke(
        app,
        ["run", "帮我做一个内部工单管理系统", "--mode", "debug"],
        env=env,
    )
    assert started.exit_code == 0, started.output
    started_data = _parse_kv_lines(started.output)
    run_id = started_data["run_id"][-1]

    assert started_data["status"][-1] == "completed"
    assert started_data["current_phase"][-1] == "deliver"
    assert "spec.md" in started_data["artifact"]
    assert "plan.md" in started_data["artifact"]
    assert "tasks.md" in started_data["artifact"]
    assert "review-report.md" in started_data["artifact"]

    status = runner.invoke(app, ["status", run_id], env=env)
    assert status.exit_code == 0, status.output
    status_data = _parse_kv_lines(status.output)
    assert status_data["status"][-1] == "completed"
    assert status_data["pending_gate"][-1] == ""

    artifacts = runner.invoke(app, ["artifacts", run_id], env=env)
    assert artifacts.exit_code == 0, artifacts.output
    artifact_rows = _parse_kv_lines(artifacts.output)["artifact"]
    assert any(row.startswith("spec.md|") for row in artifact_rows)
    assert any(row.startswith("review-report.md|") for row in artifact_rows)


def test_cli_doctor_uses_current_working_directory_defaults(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _clear_specflow_env(monkeypatch)

    result = runner.invoke(app, ["doctor"], env=_cli_default_env())

    assert result.exit_code == 0, result.output
    data = _parse_kv_lines(result.output)
    assert Path(data["working_directory"][-1]) == tmp_path
    assert Path(data["workspace_root"][-1]) == tmp_path / "runs"
    assert Path(data["data_root"][-1]) == tmp_path / ".specflow"


def test_cli_run_uses_current_working_directory_defaults(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _clear_specflow_env(monkeypatch)

    started = runner.invoke(
        app,
        ["run", "帮我做一个内部工单管理系统", "--mode", "debug"],
        env=_cli_default_env(),
    )
    assert started.exit_code == 0, started.output
    started_data = _parse_kv_lines(started.output)
    run_id = started_data["run_id"][-1]

    assert Path(started_data["workspace_root"][-1]) == tmp_path / "runs" / run_id / "workspace"
    assert (tmp_path / ".specflow" / "specflow.db").exists()
    assert (tmp_path / "runs" / run_id / "artifacts" / "spec.md").exists()
    assert (tmp_path / "runs" / run_id / "reports" / "review-report.md").exists()

    status = runner.invoke(app, ["status", run_id], env=_cli_default_env())
    assert status.exit_code == 0, status.output

    artifacts = runner.invoke(app, ["artifacts", run_id], env=_cli_default_env())
    assert artifacts.exit_code == 0, artifacts.output
    artifact_rows = _parse_kv_lines(artifacts.output)["artifact"]
    assert any(row.startswith("spec.md|") for row in artifact_rows)


def test_cli_standard_run_and_resume_flow(tmp_path: Path) -> None:
    env = _cli_env(tmp_path)

    started = runner.invoke(app, ["run", "帮我做一个内部工单管理系统"], env=env)
    assert started.exit_code == 0, started.output
    started_data = _parse_kv_lines(started.output)
    run_id = started_data["run_id"][-1]

    assert started_data["status"][-1] == "waiting_for_human"
    assert started_data["pending_gate"][-1] == "freeze_spec"

    after_freeze = runner.invoke(app, ["resume", run_id, "--approve"], env=env)
    assert after_freeze.exit_code == 0, after_freeze.output
    after_freeze_data = _parse_kv_lines(after_freeze.output)
    assert after_freeze_data["status"][-1] == "waiting_for_human"
    assert after_freeze_data["current_phase"][-1] == "review"
    assert after_freeze_data["pending_gate"][-1] == "deliver"

    completed = runner.invoke(app, ["resume", run_id, "--approve"], env=env)
    assert completed.exit_code == 0, completed.output
    completed_data = _parse_kv_lines(completed.output)
    assert completed_data["status"][-1] == "completed"
    assert completed_data["current_phase"][-1] == "deliver"
    assert completed_data["pending_gate"][-1] == ""


def test_cli_resume_rejects_conflicting_flags(tmp_path: Path) -> None:
    env = _cli_env(tmp_path)

    result = runner.invoke(
        app,
        ["resume", "run-123", "--approve", "--reject"],
        env=env,
    )

    assert result.exit_code == 1
    assert "--approve and --reject are mutually exclusive" in result.output


def test_cli_rejects_unsupported_template(tmp_path: Path) -> None:
    env = _cli_env(tmp_path)

    result = runner.invoke(
        app,
        ["run", "帮我做一个审批系统", "--template", "approval-system", "--mode", "debug"],
        env=env,
    )

    assert result.exit_code == 2
    assert "supports ticket-system only" in result.output


def _cli_env(tmp_path: Path) -> dict[str, str]:
    return {
        "SPECFLOW_DATABASE_URL": f"sqlite+pysqlite:///{tmp_path / 'specflow.db'}",
        "SPECFLOW_WORKSPACE_ROOT": str(tmp_path / "runs"),
        "SPECFLOW_DATA_ROOT": str(tmp_path / ".specflow"),
        "SPECFLOW_CHECKPOINT_BACKEND": "sqlite",
        "SPECFLOW_STORE_BACKEND": "sqlite",
        "SPECFLOW_LLM_MODEL": "",
    }


def _cli_default_env() -> dict[str, str]:
    return {
        "SPECFLOW_LLM_MODEL": "",
    }


def _clear_specflow_env(monkeypatch: MonkeyPatch) -> None:
    for name in [
        "SPECFLOW_DATABASE_URL",
        "SPECFLOW_WORKSPACE_ROOT",
        "SPECFLOW_DATA_ROOT",
        "SPECFLOW_CHECKPOINT_BACKEND",
        "SPECFLOW_CHECKPOINT_PATH",
        "SPECFLOW_CHECKPOINT_URL",
        "SPECFLOW_STORE_BACKEND",
        "SPECFLOW_STORE_PATH",
        "SPECFLOW_STORE_URL",
        "SPECFLOW_LLM_PROVIDER",
        "SPECFLOW_LLM_MODEL",
        "OPENROUTER_API_KEY",
        "SPECFLOW_OPENROUTER_API_KEY",
    ]:
        monkeypatch.delenv(name, raising=False)


def _parse_kv_lines(output: str) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for raw_line in output.splitlines():
        if "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        parsed.setdefault(key.strip(), []).append(value.strip())
    return parsed
