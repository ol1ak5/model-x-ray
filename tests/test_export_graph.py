import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "export_graph.py"
COMMITTED = ROOT / "docs" / "investigation-graph.mmd"


def run_mermaid_export(output_dir: Path) -> Path:
    subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(output_dir), "--mermaid-only"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return output_dir / "investigation-graph.mmd"


def test_export_lists_every_node_and_edge_of_the_investigation(tmp_path: Path) -> None:
    produced = run_mermaid_export(tmp_path)
    mermaid = produced.read_text()

    for node in (
        "load_sheet",
        "map_model",
        "locate",
        "trace",
        "diagnose",
        "test",
        "verify",
        "explain",
        "human_review",
        "apply_fix",
    ):
        assert node in mermaid, node
    for label in ("confirmed", "retry", "approve", "edit", "reject"):
        assert f"&nbsp;{label}&nbsp;" in mermaid, label
    assert "START" in mermaid or "__start__" in mermaid


def test_committed_mermaid_matches_the_current_graph(tmp_path: Path) -> None:
    fresh = run_mermaid_export(tmp_path).read_text()
    committed = COMMITTED.read_text()
    assert committed == fresh, (
        "docs/investigation-graph.mmd is stale — re-run scripts/export_graph.sh "
        "after any change to nodes or edges"
    )
