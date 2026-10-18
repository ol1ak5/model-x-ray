import time
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from model_x_ray import nodes
from model_x_ray.agents.investigator import build_investigator, make_diagnose_node
from model_x_ray.agents.locator import make_choose_target_node, make_locate_node
from model_x_ray.agents.mapper import make_map_model_node
from model_x_ray.memory import ModelMemory
from model_x_ray.routing import route_after_locate, route_after_review, route_after_verify
from model_x_ray.spreadsheet.sandbox import SandboxWithWrite
from model_x_ray.spreadsheet.source import SpreadsheetSource
from model_x_ray.state import InputState, InvestigationState, OutputState
from model_x_ray.tools import make_read_only_tools

NodeFunction = Callable[[InvestigationState], dict]

CONTINUATION_NODES = ("decide", "test", "verify", "diagnose", "explain", "human_review", "apply_fix")

DEFAULT_NODES: dict[str, NodeFunction] = {
    "load_sheet": nodes.load_sheet,
    "map_model": nodes.map_model,
    "locate": nodes.locate,
    "choose_target": nodes.choose_target,
    "trace": nodes.trace,
    "test": nodes.test,
    "verify": nodes.verify,
    "explain": nodes.explain,
    "human_review": nodes.human_review,
    "apply_fix": nodes.apply_fix,
}


def timed(name: str, function: NodeFunction) -> NodeFunction:
    def timed_node(state: InvestigationState) -> dict:
        started = time.perf_counter()
        update = function(state)
        latency_ms = (time.perf_counter() - started) * 1000
        return {**update, "node_log": [{"node": name, "latency_ms": latency_ms}]}

    return timed_node


def build_graph(checkpointer: BaseCheckpointSaver, diagnose: NodeFunction, overrides: dict[str, NodeFunction] | None = None, continuation: bool = False) -> CompiledStateGraph:
    node_functions = {**DEFAULT_NODES, "diagnose": diagnose, **(overrides or {})}
    if continuation:
        node_functions = {name: node_functions[name] for name in CONTINUATION_NODES}
    builder = StateGraph(InvestigationState, input_schema=InvestigationState if continuation else InputState, output_schema=OutputState)
    for name, function in node_functions.items():
        builder.add_node(name, timed(name, function))

    if continuation:
        builder.add_edge(START, "decide")
        builder.add_conditional_edges("decide", route_after_review, {"approve": "apply_fix", "edit": "test", "reject": END})
    else:
        builder.add_edge(START, "load_sheet")
        builder.add_edge("load_sheet", "map_model")
        builder.add_edge("map_model", "locate")
        builder.add_conditional_edges("locate", route_after_locate, {"found": "trace", "ask": "choose_target"})
        builder.add_edge("choose_target", "trace")
        builder.add_edge("trace", "diagnose")
        builder.add_edge("diagnose", "test")
    builder.add_edge("test", "verify")
    builder.add_conditional_edges("verify", route_after_verify, {"confirmed": "explain", "retry": "diagnose", "inconclusive": "explain"})
    builder.add_edge("explain", "human_review")
    builder.add_conditional_edges("human_review", route_after_review, {"approve": "apply_fix", "edit": "test", "reject": END})
    builder.add_edge("apply_fix", END)

    return builder.compile(checkpointer=checkpointer)


def workflow(
    llm: BaseChatModel,
    spreadsheet_id: str,
    source: SpreadsheetSource,
    sandbox: SandboxWithWrite,
    checkpointer: BaseCheckpointSaver | None,
    verifier: BaseChatModel | None,
    locator: BaseChatModel | None,
    mapper: BaseChatModel | None,
    explainer: BaseChatModel | None,
    store: BaseStore | None,
    continuation: bool,
) -> CompiledStateGraph:
    book = source.load(spreadsheet_id)
    memory = ModelMemory(store) if store is not None else None
    investigator = build_investigator(llm, make_read_only_tools(book))
    overrides: dict[str, NodeFunction] = {
        "load_sheet": nodes.make_load_sheet_node(book, memory),
        "map_model": make_map_model_node(mapper, book, memory) if mapper else nodes.map_model,
        "human_review": nodes.make_human_review_node(book, memory),
        "locate": make_locate_node(locator or llm, book),
        "choose_target": make_choose_target_node(book),
        "trace": nodes.make_trace_node(book),
        "test": nodes.make_test_node(source, sandbox),
        "verify": nodes.make_verify_node(verifier or llm, source),
        "explain": nodes.make_explain_node(explainer),
        "apply_fix": nodes.make_apply_fix_node(sandbox),
    }
    if continuation:
        overrides["decide"] = nodes.make_decide_node(book, memory)
    return build_graph(
        checkpointer or InMemorySaver(),
        diagnose=make_diagnose_node(investigator, book),
        overrides=overrides,
        continuation=continuation,
    )


def run_investigation(
    llm: BaseChatModel,
    spreadsheet_id: str,
    source: SpreadsheetSource,
    sandbox: SandboxWithWrite,
    checkpointer: BaseCheckpointSaver | None = None,
    verifier: BaseChatModel | None = None,
    locator: BaseChatModel | None = None,
    mapper: BaseChatModel | None = None,
    explainer: BaseChatModel | None = None,
    store: BaseStore | None = None,
) -> CompiledStateGraph:
    return workflow(llm, spreadsheet_id, source, sandbox, checkpointer, verifier, locator, mapper, explainer, store, continuation=False)


def run_continuation(
    llm: BaseChatModel,
    spreadsheet_id: str,
    source: SpreadsheetSource,
    sandbox: SandboxWithWrite,
    checkpointer: BaseCheckpointSaver | None = None,
    verifier: BaseChatModel | None = None,
    locator: BaseChatModel | None = None,
    mapper: BaseChatModel | None = None,
    explainer: BaseChatModel | None = None,
    store: BaseStore | None = None,
) -> CompiledStateGraph:
    return workflow(llm, spreadsheet_id, source, sandbox, checkpointer, verifier, locator, mapper, explainer, store, continuation=True)
