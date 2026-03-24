from __future__ import annotations

from typing import Annotated

import typer

from specflow import __version__
from specflow.config import get_settings
from specflow.models import ExecutionMode, TemplateType
from specflow.orchestrator import (
    PendingHumanGate,
    ProjectConfig,
    SupervisorOrchestrator,
    SupervisorRunResult,
)
from specflow.storage import ArtifactRepository, Base, RunNotFoundError, get_engine

app = typer.Typer(help="SpecFlow-Agent command line interface.", no_args_is_help=True)


def _bootstrap_runtime() -> None:
    settings = get_settings()
    settings.ensure_runtime_directories()
    Base.metadata.create_all(get_engine(settings.resolved_database_url))


def _normalize_template(value: str) -> TemplateType:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    try:
        return TemplateType(normalized)
    except ValueError as exc:
        supported = ", ".join(template.value.replace("_", "-") for template in TemplateType)
        raise typer.BadParameter(
            f"Unsupported template {value!r}. Choose one of: {supported}.",
        ) from exc


def _build_project_config(template: str) -> ProjectConfig:
    template_type = _normalize_template(template)
    if template_type is not TemplateType.TICKET_SYSTEM:
        raise typer.BadParameter(
            "V1 currently supports ticket-system only.",
            param_hint="--template",
        )
    template_slug = template_type.value.replace("_", "-")
    return ProjectConfig(
        name=f"SpecFlow {template_slug.replace('-', ' ').title()} Project",
        slug=f"specflow-{template_slug}",
        template_type=template_type,
        description=f"CLI-managed project profile for the {template_slug} template.",
    )


def _build_supervisor() -> SupervisorOrchestrator:
    _bootstrap_runtime()
    return SupervisorOrchestrator(
        settings=get_settings(),
        human_gate=PendingHumanGate(),
    )


def _build_artifact_repository() -> ArtifactRepository:
    _bootstrap_runtime()
    return ArtifactRepository(settings=get_settings())


def _echo_run_result(result: SupervisorRunResult) -> None:
    typer.echo(f"run_id={result.run_id}")
    typer.echo(f"project_id={result.project_id}")
    typer.echo(f"status={result.status.value}")
    typer.echo(f"current_phase={result.current_phase.value}")
    typer.echo(f"mode={result.mode.value}")
    typer.echo(f"workspace_root={result.workspace_root}")
    typer.echo(f"review_approved={result.review_approved}")
    typer.echo(f"summary={result.summary or ''}")
    typer.echo(f"artifact_count={len(result.artifact_names)}")
    for artifact_name in result.artifact_names:
        typer.echo(f"artifact={artifact_name}")
    if result.pending_gate is not None:
        typer.echo(f"pending_gate={result.pending_gate.gate_name}")
        typer.echo(f"pending_message={result.pending_gate.message}")
    else:
        typer.echo("pending_gate=")
        typer.echo("pending_message=")


def _load_status(orchestrator: SupervisorOrchestrator, run_id: str) -> SupervisorRunResult:
    try:
        return orchestrator.get_run_status(run_id)
    except RunNotFoundError as exc:
        typer.echo(f"error={exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def doctor() -> None:
    """Print a minimal environment and runtime diagnostic."""
    settings = get_settings()
    settings.ensure_runtime_directories()

    typer.echo(f"app_name={settings.app_name}")
    typer.echo(f"environment={settings.environment}")
    typer.echo(f"working_directory={settings.runtime_root}")
    typer.echo(f"llm_provider={settings.llm_provider}")
    typer.echo(f"llm_model={settings.llm_model or ''}")
    typer.echo(f"llm_ready={str(settings.llm_ready).lower()}")
    typer.echo(f"llm_base_url={settings.resolved_llm_base_url or ''}")
    typer.echo(f"workspace_root={settings.workspace_root}")
    typer.echo(f"data_root={settings.data_root}")
    typer.echo(f"database_url={settings.resolved_database_url}")


@app.command()
def version() -> None:
    """Print the current package version."""
    typer.echo(__version__)


@app.command()
def run(
    prompt: Annotated[str, typer.Argument(help="Natural-language requirement description.")],
    template: Annotated[
        str,
        typer.Option(
            "--template",
            help="Template profile. V1 currently supports ticket-system only.",
        ),
    ] = "ticket-system",
    mode: Annotated[
        ExecutionMode,
        typer.Option("--mode", case_sensitive=False, help="Execution mode."),
    ] = ExecutionMode.STANDARD,
    review_iterations: Annotated[
        int,
        typer.Option("--review-iterations", min=1, help="Maximum review-fix iterations."),
    ] = 1,
) -> None:
    """Start a full supervisor run."""
    orchestrator = _build_supervisor()
    result = orchestrator.start_run(
        input_prompt=prompt,
        mode=mode,
        project_config=_build_project_config(template),
        review_iterations=review_iterations,
    )
    _echo_run_result(result)
    if result.pending_gate is not None:
        typer.echo(f"next_action=specflow resume {result.run_id} --approve")


@app.command()
def status(
    run_id: Annotated[str, typer.Argument(help="Run ID returned by `specflow run`.")],
) -> None:
    """Inspect the current run state."""
    _echo_run_result(_load_status(_build_supervisor(), run_id))


@app.command()
def artifacts(
    run_id: Annotated[str, typer.Argument(help="Run ID returned by `specflow run`.")],
    latest_only: Annotated[
        bool,
        typer.Option(
            "--latest/--all-versions",
            help="List only the latest artifact versions or all stored versions.",
        ),
    ] = True,
) -> None:
    """List the generated artifacts for a run."""
    orchestrator = _build_supervisor()
    _load_status(orchestrator, run_id)
    artifacts_list = _build_artifact_repository().list_artifacts(run_id, latest_only=latest_only)

    typer.echo(f"run_id={run_id}")
    typer.echo(f"artifact_count={len(artifacts_list)}")
    for artifact in artifacts_list:
        typer.echo(
            "artifact="
            f"{artifact.name}|kind={artifact.kind.value}|version={artifact.version}|"
            f"frozen={str(artifact.is_frozen).lower()}|path={artifact.canonical_path}"
        )


@app.command()
def resume(
    run_id: Annotated[str, typer.Argument(help="Run ID returned by `specflow run`.")],
    approve: Annotated[bool, typer.Option("--approve", help="Approve the pending gate.")] = False,
    reject: Annotated[bool, typer.Option("--reject", help="Reject the pending gate.")] = False,
    review_iterations: Annotated[
        int,
        typer.Option("--review-iterations", min=1, help="Maximum review-fix iterations."),
    ] = 1,
) -> None:
    """Resume a paused run from its current checkpoint."""
    if approve and reject:
        typer.echo("error=--approve and --reject are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    orchestrator = _build_supervisor()
    current = _load_status(orchestrator, run_id)

    decision: bool | None = None
    if current.pending_gate is not None:
        if approve:
            decision = True
        elif reject:
            decision = False
        else:
            decision = typer.confirm(current.pending_gate.message, default=False)

    result = orchestrator.resume_run(
        run_id,
        decision=decision,
        review_iterations=review_iterations,
    )
    _echo_run_result(result)
    if result.pending_gate is not None:
        typer.echo(f"next_action=specflow resume {result.run_id} --approve")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
