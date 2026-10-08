import argparse
from pathlib import Path

from langchain_core.runnables.graph import Graph
from langgraph.checkpoint.memory import InMemorySaver

from model_x_ray import nodes
from model_x_ray.graph import build_graph


def build_diagram() -> Graph:
    graph = build_graph(InMemorySaver(), diagnose=nodes.stub_diagnose)
    return graph.get_graph()


def write_mermaid(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "investigation-graph.mmd"
    path.write_text(build_diagram().draw_mermaid())
    return path


def write_png(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "investigation-graph.png"
    path.write_bytes(build_diagram().draw_mermaid_png())
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the investigation graph picture from the compiled graph")
    parser.add_argument("--output-dir", type=Path, default=Path("docs"))
    parser.add_argument("--mermaid-only", action="store_true")
    args = parser.parse_args()
    print(write_mermaid(args.output_dir))
    if not args.mermaid_only:
        print(write_png(args.output_dir))


if __name__ == "__main__":
    main()
