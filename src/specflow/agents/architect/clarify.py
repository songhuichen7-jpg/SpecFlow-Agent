from __future__ import annotations

import re
from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from specflow.agents.architect.models import (
    ClarificationQuestion,
    ClarificationRound,
    ClarifiedRequirements,
)
from specflow.templates import TemplateProfileDefinition

CRITICAL_GAPS = ("roles", "workflow", "department_routing")
GAP_WEIGHTS = {
    "roles": 0.25,
    "workflow": 0.25,
    "department_routing": 0.2,
    "sla_policy": 0.15,
    "notification_rules": 0.15,
}

GAP_QUESTIONS = {
    "roles": ClarificationQuestion(
        key="roles",
        question="系统里有哪些角色？每个角色分别能创建、查看、分派或关闭哪些工单？",
        reason="需要明确 RBAC 和页面权限边界。",
    ),
    "workflow": ClarificationQuestion(
        key="workflow",
        question="工单的标准状态流转是什么？哪些状态允许回退、关闭或重新打开？",
        reason="需要冻结状态机与 API 状态变更约束。",
    ),
    "department_routing": ClarificationQuestion(
        key="department_routing",
        question="工单是否按部门或处理组路由？如果是，分派规则如何确定？",
        reason="影响部门实体、过滤条件和分配规则。",
    ),
    "sla_policy": ClarificationQuestion(
        key="sla_policy",
        question="是否存在优先级和 SLA 规则？例如高优先级工单需要更短响应时间吗？",
        reason="影响优先级枚举、仪表盘指标和提醒逻辑。",
    ),
    "notification_rules": ClarificationQuestion(
        key="notification_rules",
        question="系统是否需要邮件、IM 或站内通知？哪些事件需要触发通知？",
        reason="决定 v1 是否纳入异步通知能力。",
    ),
}

ROLE_KEYWORDS = {
    "requester": ("requester", "employee", "submitter", "用户", "员工", "申请人", "提单人"),
    "assignee": ("assignee", "agent", "resolver", "operator", "处理人", "客服", "支持", "工程师"),
    "admin": ("admin", "administrator", "管理员", "系统管理员"),
}

STATUS_SYNONYMS = {
    "open": ("open", "new", "todo", "待处理", "新建", "待办"),
    "in_progress": ("in_progress", "assigned", "progress", "处理中", "进行中", "处理中"),
    "resolved": ("resolved", "done", "solved", "已解决", "待验证"),
    "closed": ("closed", "archived", "已关闭", "关闭"),
}


class ClarificationState(TypedDict, total=False):
    raw_request: str
    supplemental_inputs: list[str]
    consumed_inputs: list[str]
    max_rounds: int
    round_index: int
    identified_gaps: list[str]
    questions: list[dict[str, Any]]
    rounds: list[dict[str, Any]]
    structured_requirements: dict[str, Any]
    completeness_score: float
    is_complete: bool
    current_text: str


class ClarificationGraph:
    """LangGraph clarify loop used by the Architect agent."""

    def run(
        self,
        *,
        request: str,
        template_profile: TemplateProfileDefinition,
        target_stack: str,
        supplemental_inputs: list[str] | None = None,
        max_rounds: int = 2,
    ) -> ClarifiedRequirements:
        graph = self._build_graph(template_profile=template_profile, target_stack=target_stack)
        result = cast(
            dict[str, Any],
            graph.invoke(
                {
                    "raw_request": request,
                    "supplemental_inputs": supplemental_inputs or [],
                    "consumed_inputs": [],
                    "max_rounds": max_rounds,
                    "round_index": 0,
                    "identified_gaps": [],
                    "questions": [],
                    "rounds": [],
                }
            ),
        )
        payload = dict(result["structured_requirements"])
        payload["rounds"] = result.get("rounds", [])
        return ClarifiedRequirements.model_validate(payload)

    def _build_graph(
        self,
        *,
        template_profile: TemplateProfileDefinition,
        target_stack: str,
    ) -> Any:
        def analyze(state: ClarificationState) -> dict[str, Any]:
            requirements, gaps = build_clarified_requirements(
                raw_request=state["raw_request"],
                supplemental_inputs=state.get("consumed_inputs", []),
                template_profile=template_profile,
                target_stack=target_stack,
                rounds=state.get("rounds", []),
            )
            current_text = "\n".join([state["raw_request"], *state.get("consumed_inputs", [])])
            return {
                "current_text": current_text,
                "identified_gaps": gaps,
                "structured_requirements": requirements.model_dump(mode="python"),
                "completeness_score": requirements.completeness_score,
                "is_complete": requirements.is_complete,
            }

        def route_after_analysis(state: ClarificationState) -> str:
            if state["is_complete"]:
                return "finalize"
            if state["round_index"] >= state["max_rounds"]:
                return "finalize"
            if len(state.get("consumed_inputs", [])) >= len(state.get("supplemental_inputs", [])):
                return "finalize"
            return "generate_questions"

        def generate_questions(state: ClarificationState) -> dict[str, Any]:
            questions = [
                GAP_QUESTIONS[gap].model_dump(mode="python")
                for gap in state.get("identified_gaps", [])
                if gap in GAP_QUESTIONS
            ][:3]
            rounds = list(state.get("rounds", []))
            rounds.append(
                ClarificationRound(
                    round_number=state["round_index"] + 1,
                    gaps=list(state.get("identified_gaps", [])),
                    questions=[
                        ClarificationQuestion.model_validate(question) for question in questions
                    ],
                ).model_dump(mode="python")
            )
            return {"questions": questions, "rounds": rounds}

        def consume_input(state: ClarificationState) -> dict[str, Any]:
            index = len(state.get("consumed_inputs", []))
            inputs = state.get("supplemental_inputs", [])
            if index >= len(inputs):
                return {}
            answer = inputs[index]
            rounds = list(state.get("rounds", []))
            if rounds:
                rounds[-1] = {**rounds[-1], "answer": answer}
            return {
                "consumed_inputs": [*state.get("consumed_inputs", []), answer],
                "round_index": state["round_index"] + 1,
                "rounds": rounds,
                "questions": [],
            }

        builder = StateGraph(ClarificationState)
        builder.add_node("analyze", analyze)
        builder.add_node("generate_questions", generate_questions)
        builder.add_node("consume_input", consume_input)
        builder.add_node("finalize", lambda _state: {})
        builder.add_edge(START, "analyze")
        builder.add_conditional_edges(
            "analyze",
            route_after_analysis,
            {
                "generate_questions": "generate_questions",
                "finalize": "finalize",
            },
        )
        builder.add_edge("generate_questions", "consume_input")
        builder.add_edge("consume_input", "analyze")
        builder.add_edge("finalize", END)
        return builder.compile()


def build_clarified_requirements(
    *,
    raw_request: str,
    supplemental_inputs: list[str],
    template_profile: TemplateProfileDefinition,
    target_stack: str,
    rounds: list[dict[str, Any]] | None = None,
) -> tuple[ClarifiedRequirements, list[str]]:
    combined_text = "\n".join([raw_request, *supplemental_inputs]).strip()
    explicit_roles = _detect_roles(combined_text)
    explicit_states = _detect_states(combined_text, template_profile.state_machine)

    gaps: list[str] = []
    if len(explicit_roles) < 2:
        gaps.append("roles")
    if len(explicit_states) < 2:
        gaps.append("workflow")
    if not _contains_any(combined_text, ("department", "queue", "部门", "处理组")):
        gaps.append("department_routing")
    if not _contains_any(combined_text, ("sla", "优先级", "时效", "响应时间")):
        gaps.append("sla_policy")
    if not _contains_any(
        combined_text,
        ("notification", "notify", "email", "slack", "dingtalk", "通知"),
    ):
        gaps.append("notification_rules")

    completeness_score = round(1.0 - sum(GAP_WEIGHTS[gap] for gap in gaps), 2)
    is_complete = all(gap not in gaps for gap in CRITICAL_GAPS) and completeness_score >= 0.75

    roles = explicit_roles or list(template_profile.roles)
    state_machine = explicit_states or list(template_profile.state_machine)
    features = {
        "attachments": _contains_any(combined_text, ("attachment", "upload", "附件", "上传"))
        or True,
        "comments": _contains_any(combined_text, ("comment", "timeline", "评论", "留言")) or True,
        "dashboard": _contains_any(
            combined_text, ("dashboard", "metric", "report", "仪表盘", "统计")
        )
        or True,
        "departments": True,
        "sla": "sla_policy" not in gaps,
        "notifications": "notification_rules" not in gaps,
    }

    assumptions = [
        f"首个可交付版本固定采用 {target_stack} 技术栈。",
        "系统先服务单组织内部团队，不引入多租户隔离。",
        "所有状态变更、评论和附件上传都需要保留审计痕迹。",
    ]
    if "department_routing" in gaps:
        assumptions.append("默认按提交人所属部门和支持队列进行路由。")
    if "sla_policy" in gaps:
        assumptions.append("默认提供 P1-P4 优先级与可视化 SLA 标签，后续再细化时效矩阵。")
    if "notification_rules" in gaps:
        assumptions.append("v1 暂不强制接入异步通知，优先保证站内可见性与仪表盘告警。")

    business_rules = [
        f"工单状态机固定为 {' -> '.join(state_machine)}。",
        "RBAC 至少包含 requester、assignee、admin 三类角色，并以部门范围控制访问。",
        "列表接口必须支持分页、关键字搜索、状态过滤、优先级过滤和部门过滤。",
        "评论与附件必须挂靠在工单时间线上，且变更可审计。",
    ]
    if features["sla"]:
        business_rules.append("仪表盘需要展示 SLA 风险或超时视图。")
    else:
        business_rules.append("优先级字段保留在数据模型中，即使初版不实现完整 SLA 引擎。")

    open_questions = [] if is_complete else [GAP_QUESTIONS[gap].question for gap in gaps]
    requested_capabilities = [
        capability
        for capability, enabled in (
            ("附件管理", features["attachments"]),
            ("评论时间线", features["comments"]),
            ("仪表盘", features["dashboard"]),
            ("SLA 指标", features["sla"]),
            ("通知规则", features["notifications"]),
        )
        if enabled
    ]

    requirement_summary = (
        "围绕简化版内部工单系统生成规格，覆盖工单流转、角色权限、部门维度、"
        "标准 CRUD 页面与 API 契约。"
    )

    requirements = ClarifiedRequirements(
        title="简化版内部工单系统",
        original_request=raw_request,
        requirement_summary=requirement_summary,
        template_slug=template_profile.slug,
        template_version=template_profile.version,
        target_stack=target_stack,
        roles=roles,
        entities=[entity.title for entity in template_profile.entities],
        pages=[f"{page.title} ({page.route})" for page in template_profile.pages],
        apis=[api.base_path for api in template_profile.api_definitions],
        state_machine=state_machine,
        business_rules=business_rules,
        acceptance_criteria=list(template_profile.acceptance_criteria),
        assumptions=assumptions,
        open_questions=open_questions,
        supplemental_notes=[note for note in supplemental_inputs if note.strip()],
        requested_capabilities=requested_capabilities,
        features=features,
        rounds=[ClarificationRound.model_validate(round_item) for round_item in rounds or []],
        completeness_score=completeness_score,
        is_complete=is_complete,
    )
    return requirements, gaps


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(pattern.lower() in normalized for pattern in patterns)


def _detect_roles(text: str) -> list[str]:
    normalized = text.lower()
    detected: list[str] = []
    for role, keywords in ROLE_KEYWORDS.items():
        if any(keyword.lower() in normalized for keyword in keywords):
            detected.append(role)
    return detected


def _detect_states(text: str, fallback_states: tuple[str, ...]) -> list[str]:
    normalized = text.lower()
    explicit: list[str] = []
    for state in fallback_states:
        keywords = STATUS_SYNONYMS.get(state, (state,))
        if any(keyword.lower() in normalized for keyword in keywords):
            explicit.append(state)
    if len(explicit) >= 2:
        return explicit

    arrow_tokens = [
        token.strip().lower()
        for token in re.split(r"->|→|=>|＞|>|,|，|/|\n", text)
        if token.strip()
    ]
    parsed: list[str] = []
    for token in arrow_tokens:
        for state, keywords in STATUS_SYNONYMS.items():
            if token == state or token in {keyword.lower() for keyword in keywords}:
                if state not in parsed:
                    parsed.append(state)
                break
    return parsed
