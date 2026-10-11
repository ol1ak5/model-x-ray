import type { CausalNode } from "../api";
import { money } from "../format";

function Node({ node, after }: { node: CausalNode; after: Record<string, number> }) {
  const fixed = after[node.cell];
  const share = Math.max(0, Math.min(1, Math.abs(node.share_of_change)));
  return (
    <li>
      <div className={`node ${node.suspicious ? "suspicious" : ""}`}>
        <span className="node-label">{node.label}</span>
        <span className="mono node-cell">{node.cell}</span>
        <span className="numbers">
          {money(node.value_before)} → {money(node.value_after)}
        </span>
        <span className="share" aria-label={`${Math.round(share * 100)}% of the change`}>
          <span className="share-bar" style={{ width: `${share * 100}%` }} />
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
    <section aria-labelledby="tree-title">
      <h2 id="tree-title" className="visually-hidden">
        Cause tree
      </h2>
      <p className="hint">What moved the number from the prior period. Bars show each input's share of the change; suspicious cells break the pattern of their row.</p>
      <ul className="tree">
        <Node node={root} after={after} />
      </ul>
    </section>
  );
}
