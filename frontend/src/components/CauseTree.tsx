import type { CausalNode } from "../api";

function Node({ node, after }: { node: CausalNode; after: Record<string, number> }) {
  const fixed = after[node.cell];
  return (
    <li>
      <div className={`node ${node.suspicious ? "suspicious" : ""}`}>
        <span className="node-label">{node.label}</span>
        <span className="mono">{node.cell}</span>
        <span className="numbers">
          {node.value_before.toFixed(2)} → {node.value_after.toFixed(2)} ({node.delta >= 0 ? "+" : ""}
          {node.delta.toFixed(2)}, {Math.round(node.share_of_change * 100)}% of the change)
        </span>
        {node.suspicious && <span className="flag">Suspicious</span>}
        {fixed !== undefined && fixed !== node.value_after && <span className="after-fix">after fix {fixed.toFixed(2)}</span>}
      </div>
      {node.children.length > 0 && (
        <ul>
          {node.children.map((child) => (
            <Node key={child.cell} node={child} after={after} />
          ))}
        </ul>
      )}
    </li>
  );
}

export default function CauseTree({ root, after }: { root: CausalNode; after: Record<string, number> }) {
  return (
    <section className="card" aria-labelledby="tree-title">
      <h2 id="tree-title">Cause tree</h2>
      <p className="hint">What moved the number, from the prior period to this one. Suspicious cells break the pattern of their row.</p>
      <ul className="tree">
        <Node node={root} after={after} />
      </ul>
    </section>
  );
}
