from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from specflow.agents.coder import CoderAgent, CoderRunResult
from specflow.agents.reviewer import ReviewerAgent, ReviewRunResult
from specflow.config import Settings, get_settings
from specflow.storage import ArtifactRepository, RunStateManager


class ReviewFixLoopState(TypedDict, total=False):
    run_id: str
    max_iterations: int
    fix_attempts: int
    latest_review: dict[str, Any]
    review_results: list[dict[str, Any]]
    fix_results: list[dict[str, Any]]
    requires_human_arbitration: bool


class ReviewFixLoopResult(BaseModel):
    """Structured result for the Sprint 5 review-fix LangGraph loop."""

    run_id: str
    approved: bool
    blocking: bool
    iterations: int
    requires_human_arbitration: bool
    reviews: list[ReviewRunResult] = Field(default_factory=list)
    fixes: list[CoderRunResult] = Field(default_factory=list)


class ReviewFixLoop:
    """Run Reviewer -> Coder fix cycles with a bounded retry budget."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        artifact_repository: ArtifactRepository | None = None,
        run_state_manager: RunStateManager | None = None,
        coder: CoderAgent | None = None,
        reviewer: ReviewerAgent | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_runtime_directories()
        self.artifact_repository = artifact_repository or ArtifactRepository(settings=self.settings)
        self.run_state_manager = run_state_manager or RunStateManager(
            settings=self.settings,
            artifact_repository=self.artifact_repository,
        )
        self.coder = coder or CoderAgent(
            settings=self.settings,
            artifact_repository=self.artifact_repository,
            run_state_manager=self.run_state_manager,
        )
        self.reviewer = reviewer or ReviewerAgent(
            settings=self.settings,
            artifact_repository=self.artifact_repository,
            run_state_manager=self.run_state_manager,
        )
        self.graph = self._build_graph()

    def run(self, run_id: str, *, max_iterations: int = 1) -> ReviewFixLoopResult:
        result = cast(
            dict[str, Any],
            self.graph.invoke(
                {
                    "run_id": run_id,
                    "max_iterations": max_iterations,
                    "fix_attempts": 0,
                    "review_results": [],
                    "fix_results": [],
                    "requires_human_arbitration": False,
                }
            ),
        )
        reviews = [
            ReviewRunResult.model_validate(item) for item in result.get("review_results", [])
        ]
        fixes = [CoderRunResult.model_validate(item) for item in result.get("fix_results", [])]
        latest_review = reviews[-1]
        return ReviewFixLoopResult(
            run_id=run_id,
            approved=latest_review.approved,
            blocking=latest_review.blocking,
            iterations=result.get("fix_attempts", 0),
            requires_human_arbitration=bool(result.get("requires_human_arbitration", False)),
            reviews=reviews,
            fixes=fixes,
        )

    def _build_graph(self) -> Any:
        def review_node(state: ReviewFixLoopState) -> dict[str, Any]:
            review = self.reviewer.run(state["run_id"])
            results = list(state.get("review_results", []))
            results.append(review.model_dump(mode="python"))
            return {
                "latest_review": review.model_dump(mode="python"),
                "review_results": results,
            }

        def route_after_review(state: ReviewFixLoopState) -> str:
            latest = ReviewRunResult.model_validate(state["latest_review"])
            if latest.approved:
                return "finalize"
            if state["fix_attempts"] >= state["max_iterations"]:
                return "escalate"
            return "fix"

        def fix_node(state: ReviewFixLoopState) -> dict[str, Any]:
            latest = ReviewRunResult.model_validate(state["latest_review"])
            coder_result = self.coder.fix_issues(
                state["run_id"],
                issue_titles=[issue.title for issue in latest.issues],
            )
            fixes = list(state.get("fix_results", []))
            fixes.append(coder_result.model_dump(mode="python"))
            return {
                "fix_attempts": state["fix_attempts"] + 1,
                "fix_results": fixes,
            }

        def escalate_node(state: ReviewFixLoopState) -> dict[str, Any]:
            latest = ReviewRunResult.model_validate(state["latest_review"])
            self.run_state_manager.request_human_gate(
                state["run_id"],
                message=(
                    "Review-fix loop exhausted its retry budget. "
                    f"Remaining issues: {', '.join(issue.title for issue in latest.issues)}"
                ),
                payload={
                    "gate_name": "review_arbitration",
                    "issues": [issue.model_dump(mode="python") for issue in latest.issues],
                    "max_iterations": state["max_iterations"],
                },
            )
            return {"requires_human_arbitration": True}

        builder = StateGraph(ReviewFixLoopState)
        builder.add_node("review", review_node)
        builder.add_node("fix", fix_node)
        builder.add_node("escalate", escalate_node)
        builder.add_node("finalize", lambda _state: {})
        builder.add_edge(START, "review")
        builder.add_conditional_edges(
            "review",
            route_after_review,
            {
                "fix": "fix",
                "escalate": "escalate",
                "finalize": "finalize",
            },
        )
        builder.add_edge("fix", "review")
        builder.add_edge("escalate", END)
        builder.add_edge("finalize", END)
        return builder.compile()
