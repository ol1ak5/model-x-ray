import type { InvestigationView } from "../api";
import CauseTree from "./CauseTree";
import EvidencePanel from "./EvidencePanel";
import HypothesisBoard from "./HypothesisBoard";

export type Tab = "tree" | "findings" | "evidence";

export default function DetailTabs({ view, tab, onTab }: { view: InvestigationView; tab: Tab; onTab: (tab: Tab) => void }) {
  const tabs: { id: Tab; label: string; count?: number; show: boolean }[] = [
    { id: "tree", label: "Cause tree", show: Boolean(view.causal_tree) },
    { id: "findings", label: "Findings", count: view.hypotheses?.length ?? 0, show: (view.hypotheses?.length ?? 0) > 0 },
    { id: "evidence", label: "Evidence", count: view.evidence?.length ?? 0, show: (view.evidence?.length ?? 0) > 0 },
  ];
  const visible = tabs.filter((item) => item.show);
  if (visible.length === 0) return null;
  const current = visible.some((item) => item.id === tab) ? tab : visible[0].id;
  const after = view.verifications?.at(-1)?.after ?? {};

  return (
    <div className="card details">
      <div className="tabs" role="tablist" aria-label="Details">
        {visible.map((item) => (
          <button key={item.id} type="button" role="tab" id={`tab-${item.id}`} aria-selected={current === item.id} aria-controls={`panel-${item.id}`} className={current === item.id ? "active" : ""} onClick={() => onTab(item.id)}>
            {item.label}
            {item.count !== undefined && <span className="count">{item.count}</span>}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${current}`} aria-labelledby={`tab-${current}`} className="tab-panel">
        {current === "tree" && view.causal_tree && <CauseTree root={view.causal_tree} after={after} />}
        {current === "findings" && <HypothesisBoard hypotheses={view.hypotheses ?? []} />}
        {current === "evidence" && <EvidencePanel evidence={view.evidence ?? []} />}
      </div>
    </div>
  );
}
