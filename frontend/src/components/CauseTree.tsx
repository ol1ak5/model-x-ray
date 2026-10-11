import type { CausalNode } from "../api";
import { money } from "../format";
import Chip from "./Chip";
import styles from "./CauseTree.module.css";

function Node({ node, after }: { node: CausalNode; after: Record<string, number> }) {
  const fixed = after[node.cell];
  const share = Math.max(0, Math.min(1, Math.abs(node.share_of_change)));
  return (
    <li>
      <div className={`${styles.node} ${node.suspicious ? styles.suspiciousNode : ""}`}>
        <span className={styles.nodeLabel}>{node.label}</span>
        <span className={`mono ${styles.nodeCell}`}>{node.cell}</span>
        <span className={styles.numbers}>
          {money(node.value_before)} → {money(node.value_after)}
        </span>
        <span className={styles.share} aria-label={`${Math.round(share * 100)}% of the change`}>
          <span className={styles.shareBar} style={{ width: `${share * 100}%` }} />
        </span>
        {node.suspicious && <Chip tone="red">Suspicious</Chip>}
        {fixed !== undefined && fixed !== node.value_after && (
          <Chip tone="green">after fix {fixed.toFixed(2)}</Chip>
        )}
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
      <p className={styles.hint}>What moved the number from the prior period. Bars show each input's share of the change; suspicious cells break the pattern of their row.</p>
      <ul className={styles.tree}>
        <Node node={root} after={after} />
      </ul>
    </section>
  );
}
