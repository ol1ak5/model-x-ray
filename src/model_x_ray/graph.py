from collections.abc import Callable

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from model_x_ray import nodes
from model_x_ray.routing import route_after_review, route_after_verify
from model_x_ray.state import InputState, InvestigationState, OutputState

NodeFunction = Callable[[InvestigationState], dict]

DEFAULT_NODES: dict[str, NodeFunction] = {
    "load_sheet": nodes.load_sheet,
    "map_model": nodes.map_model,
    "locate": nodes.locate,
    "trace": nodes.trace,
    "diagnose": nodes.diagnose,
    "test": nodes.test,
    "verify": nodes.verify,
    "explain": nodes.explain,
    "human_review": nodes.human_review,
    "apply_fix": nodes.apply_fix,
}


def build_graph(checkpointer: BaseCheckpointSaver, overrides: dict[str, NodeFunction] | None = None) -> CompiledStateGraph:
    node_functions = {**DEFAULT_NODES, **(overrides or {})}
    builder = StateGraph(InvestigationState, input_schema=InputState, output_schema=OutputState)
    for name, function in node_functions.items():
        builder.add_node(name, function)

    builder.add_edge(START, "load_sheet")
    builder.add_edge("load_sheet", "map_model")
    builder.add_edge("map_model", "locate")
    builder.add_edge("locate", "trace")
    builder.add_edge("trace", "diagnose")
    builder.add_edge("diagnose", "test")
    builder.add_edge("test", "verify")
    builder.add_conditional_edges("verify", route_after_verify, {"confirmed": "explain", "retry": "diagnose", "inconclusive": "explain"})
    builder.add_edge("explain", "human_review")
    builder.add_conditional_edges("human_review", route_after_review, {"apply_fix": "apply_fix", "test": "test", END: END})
    builder.add_edge("apply_fix", END)

    return builder.compile(checkpointer=checkpointer)
