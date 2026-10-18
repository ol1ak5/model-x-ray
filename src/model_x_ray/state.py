import operator
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class TargetCell(TypedDict):
    sheet: str
    cell: str
    label: str
    period: str
    value: float
    prior_cell: str
    prior_value: float
    mode: NotRequired[str]
    finding: NotRequired[str]
    expected_formula: NotRequired[str | None]
    other_findings: NotRequired[list[dict]]


class RowRole(TypedDict):
    label: str
    kind: Literal["revenue", "cost", "subtotal", "ratio", "other"]


class ColumnRole(TypedDict):
    period: str
    kind: Literal["actual", "forecast"]


class ModelMap(TypedDict):
    rows: list[RowRole]
    columns: list[ColumnRole]


class TargetChoice(TypedDict):
    candidates: list[str]
    chosen: str
    why: str


class Override(TypedDict):
    cell: str
    content: str
    reason: str


class Finding(TypedDict):
    cell: str
    error_type: str
    old_formula: str
    new_formula: str


class Contribution(TypedDict):
    cell: str
    label: str
    delta: float


class CausalNode(TypedDict):
    cell: str
    label: str
    value_before: float
    value_after: float
    delta: float
    share_of_change: float
    suspicious: bool
    children: list["CausalNode"]


class Hypothesis(TypedDict):
    id: str
    cell: str
    error_type: Literal["typed_value", "wrong_reference", "range_inconsistency", "sign_inconsistency", "period_inconsistency"]
    claim: str
    evidence_ids: list[str]
    confidence: Literal["high", "medium", "low"]
    status: Literal["open", "rejected", "confirmed"]


class Patch(TypedDict):
    cell: str
    old_formula: str
    new_formula: str
    source: Literal["agent", "human"]


class Verification(TypedDict):
    hypothesis_id: str
    before: dict[str, float]
    after: dict[str, float]
    checks: dict[str, bool]
    verdict: Literal["confirmed", "rejected", "inconclusive"]
    reason: str
    error: NotRequired[str]


class Evidence(TypedDict):
    id: str
    cell: str
    kind: Literal["anomaly", "expected_pattern", "verification"]
    text: str


class HumanDecision(TypedDict):
    action: Literal["approve", "edit", "reject"]
    reason: str
    patch: Patch | None


class RunLog(TypedDict):
    role: Literal["investigator", "verifier", "mapper", "locate", "explain"]
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    latency_ms: float


class NodeLog(TypedDict):
    node: str
    latency_ms: float


def merge_by_id(left: list[Hypothesis], right: list[Hypothesis]) -> list[Hypothesis]:
    merged = {h["id"]: h for h in left}
    for update in right:
        merged[update["id"]] = {**merged.get(update["id"], {}), **update}
    return list(merged.values())


def merge_verifications(left: list[Verification], right: list[Verification]) -> list[Verification]:
    merged = {v["hypothesis_id"]: v for v in left}
    for update in right:
        merged[update["hypothesis_id"]] = {**merged.get(update["hypothesis_id"], {}), **update}
    return list(merged.values())


class InvestigationState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    spreadsheet_id: str
    question: str
    model_map: ModelMap | None
    known_overrides: list[Override]
    past_findings: list[Finding]
    target: TargetCell | None
    target_choice: TargetChoice | None
    contributions: list[Contribution]
    causal_tree: CausalNode | None
    hypotheses: Annotated[list[Hypothesis], merge_by_id]
    patch: Patch | None
    verifications: Annotated[list[Verification], merge_verifications]
    evidence: Annotated[list[Evidence], operator.add]
    run_log: Annotated[list[RunLog], operator.add]
    node_log: Annotated[list[NodeLog], operator.add]
    tool_call_counts: Annotated[list[int], operator.add]
    attempts: int
    report: str | None
    human_decision: HumanDecision | None
    corrected_copy_id: str | None


class InputState(TypedDict):
    spreadsheet_id: str
    question: str


class OutputState(TypedDict):
    report: str | None
    patch: Patch | None
    evidence: list[Evidence]
    corrected_copy_id: str | None
