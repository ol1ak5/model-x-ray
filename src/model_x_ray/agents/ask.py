import re
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from model_x_ray.llm import invoke_with_usage, model_name_of
from model_x_ray.nodes import target_statement
from model_x_ray.prompts import load_prompt
from model_x_ray.state import RunLog

ASK_MAX_TOKENS = 4000

NO_ANSWER = "I could not answer that from this check. Ask about the cell, its formula, the fix or the numbers it changes."

SPEAKERS = {"user": "Reviewer", "agent": "Model X-Ray"}


def ask_brief(state: dict[str, Any], history: list[dict[str, str]], question: str, labels: dict[str, str] | None = None) -> str:
    named = labels or {}

    def cell(ref: str) -> str:
        return f"{ref} ({named[ref]})" if named.get(ref) else ref

    lines = []
    target = state.get("target")
    if target:
        lines.append(f"What the check looked at: {target_statement(target)} ({target['sheet']}!{target['cell']}).")
    patch = state.get("patch")
    if patch:
        lines.append(f"The error: {cell(patch['cell'])} contains {patch['old_formula']}.")
        lines.append(f"The fix tested in a copy: {patch['cell']} = {patch['new_formula']}.")
    for hypothesis in state.get("hypotheses", []):
        lines.append(f"Finding ({hypothesis.get('status', 'open')}): {hypothesis['cell']}, {hypothesis['error_type'].replace('_', ' ')}: {hypothesis['claim']}")
    verifications = state.get("verifications", [])
    if verifications:
        latest = verifications[-1]
        changes = [f"{cell(ref)} from {latest['before'].get(ref)} to {value}" for ref, value in latest.get("after", {}).items() if latest["before"].get(ref) != value]
        if changes:
            lines.append(f"Numbers in the copy after the fix: {', '.join(changes)}.")
        if latest.get("verdict"):
            lines.append(f"Verification: {latest['verdict']}" + (f", {latest['reason']}" if latest.get("reason") else "") + ".")
    for record in state.get("evidence", []):
        lines.append(f"Evidence on {record['cell']}: {record['text']}")
    if state.get("report"):
        lines.append(f"Report the reviewer read: {state['report']}")
    decision = state.get("human_decision")
    if decision:
        lines.append(f"The reviewer's decision so far: {decision.get('action')}.")
    if history:
        lines.append("Conversation so far:")
        lines += [f"{SPEAKERS.get(turn.get('role', ''), 'Reviewer')}: {turn.get('text', '')}" for turn in history]
    lines.append(f"Reviewer's question: {question}")
    return "\n".join(lines)


def plain(text: str) -> str:
    text = re.sub(r"\*\*|__|`", "", text)
    text = re.sub(r"\s*(?:->|→|=>)\s*", " to ", text)
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    text = re.sub(r";\s+(\w)", lambda match: ". " + match.group(1).upper(), text)
    text = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*\((?:evidence:\s*)?ev-\d+(?:,\s*ev-\d+)*\)", "", text)
    return " ".join(text.split())


def answer_question(llm: BaseChatModel, state: dict[str, Any], history: list[dict[str, str]], question: str, labels: dict[str, str] | None = None) -> tuple[str, list[RunLog]]:
    reply, records = invoke_with_usage(
        llm.bind(max_tokens=ASK_MAX_TOKENS),
        [SystemMessage(content=load_prompt("ask")), HumanMessage(content=ask_brief(state, history, question, labels))],
        role="explain",
        model=model_name_of(llm),
    )
    text = plain(reply.content if isinstance(reply.content, str) else "")
    return (text or NO_ANSWER), records
