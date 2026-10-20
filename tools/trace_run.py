import argparse
import json
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from model_x_ray.agents.investigator import logic_review_brief
from model_x_ray.benchmark.runner import SETUP_RULES, SETUP_SUPER, build_setup_graph, cost_of, drive_graph
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource
from model_x_ray.spreadsheet.xlsx import load_xlsx

SETUPS = {"rules": SETUP_RULES, "super": SETUP_SUPER}


def section(title: str, lines: list[str]) -> None:
    print(f"\n== {title}")
    for line in lines:
        print(line)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one investigation and print every step of the agent's reasoning: target, logic brief, each vote, each decision, each verification and the report")
    parser.add_argument("file", type=Path, help="an .xlsx model")
    parser.add_argument("--setup", choices=list(SETUPS), default="rules", help="'super' spends Token Factory credits (about 0.04 USD for a small model)")
    parser.add_argument("--question", default="", help="leave empty to check the whole model")
    parser.add_argument("--work", type=Path, default=Path(".trace-work"), help="where corrected copies are written; never committed")
    args = parser.parse_args()
    load_dotenv()

    source = XlsxSource({"model": args.file})
    graph = build_setup_graph(SETUPS[args.setup], source, XlsxSandbox(source, args.work), "model")
    final = drive_graph(graph, {"spreadsheet_id": "model", "question": args.question}, {"configurable": {"thread_id": uuid4().hex}})

    target = final["target"]
    section("Target", [f"{target['sheet']}!{target['cell']} {target['label']} {target.get('period', '')} (mode: {target.get('mode', 'period')})", f"Question: {final.get('question', '')}"])
    section("Logic brief the investigator sees when no rule flags a cell", logic_review_brief(load_xlsx(args.file), final).splitlines())
    for number, decision in enumerate(final.get("decisions", []), start=1):
        lines = [f"decided by {decision['decided_by']}: {decision.get('cell')} {decision.get('fix') or ''}", f"rule would have: {decision.get('rule_would_have')}", f"reason: {decision.get('reason', '')}"]
        lines += [f"judgement {j['number']} {j['cell']}: {j['verdict']}, {j['reason']}" for j in decision.get("judgements", [])]
        if "votes" in decision:
            lines.append(f"votes: {json.dumps(decision['votes'])}")
            for index, ballot in enumerate(decision.get("ballots", []), start=1):
                found = "; ".join(f"{h['cell']} {h['error_type']} ({h['confidence']}): {h['claim']}" for h in ballot["hypotheses"]) or "no error"
                lines.append(f"  vote {index}: {found} | fix {ballot['patch']} | {ballot['reason']}")
        section(f"Decision {number}", lines)
    section("Verifications", [f"{v.get('hypothesis_id')}: {v.get('verdict')} {v.get('checks', {})} {v.get('reason', '')}" for v in final.get("verifications", []) if v.get("verdict")])
    section("Report", [final.get("report", "")])
    print(f"\ncost: {cost_of(final.get('run_log', [])):.4f} USD")


if __name__ == "__main__":
    main()
