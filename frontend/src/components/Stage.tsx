import { useLayoutEffect, useMemo, useRef, useState } from "react";

import type { CausalNode, InvestigationView, SheetWindow } from "../api";
import { kindOf } from "../format";
import SheetGrid, { type Marks } from "./SheetGrid";
import styles from "./Stage.module.css";

type Edge = { id: string; from: string; fromLabel: string; to: string; delta: number; share: number; suspicious: boolean; depth: number };
type Box = { x: number; y: number; w: number; h: number };
type Wire = { id: string; d: string; dot: { x: number; y: number }; rail: number; suspicious: boolean; delay: number };
type Label = { id: string; x: number; y: number; title: string; detail: string | null; claim: string | null; bad: boolean; delay: number };

const STILL = import.meta.env.DEV && new URLSearchParams(window.location.search).has("static");
const NOTE_WIDTH = 144;

function edgesOf(node: CausalNode | null, depth = 0): Edge[] {
  if (!node) return [];
  return node.children.flatMap((child) => [
    { id: `${child.cell}->${node.cell}`, from: child.cell, fromLabel: child.label, to: node.cell, delta: child.delta, share: child.share_of_change, suspicious: child.suspicious, depth },
    ...edgesOf(child, depth + 1),
  ]);
}

function route(edge: Edge, from: Box, to: Box, lane: number, lanes: number): Wire {
  const sx = from.x + from.w;
  const sy = from.y + from.h / 2;
  const ty = to.y + to.h / 2 + (lane - (lanes - 1) / 2) * 8;
  const edgeX = to.x + to.w;
  const rail = Math.max(sx, edgeX) + 18 + Math.min(lane, 4) * 9;
  return { id: edge.id, d: `M ${sx} ${sy} H ${rail} V ${ty} H ${edgeX}`, dot: { x: sx, y: sy }, rail, suspicious: edge.suspicious, delay: 0 };
}

function shortLabel(text: string): string {
  return text.length > 16 ? `${text.slice(0, 15)}…` : text;
}

function signed(value: number): string {
  const text = Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return `${value < 0 ? "-" : "+"}${text}`;
}

function reasonOf(edge: Edge, claim: string | null, errorType: string | null, ratioTarget: boolean): { detail: string | null; claim: string | null } {
  if (errorType !== null) return { detail: errorType.replaceAll("_", " "), claim };
  if (ratioTarget) return { detail: null, claim: null };
  if (edge.share >= 0.04) return { detail: `${Math.round(edge.share * 100)}% of the move`, claim: null };
  return { detail: null, claim: null };
}

export default function Stage({
  view,
  sheet,
  marks,
  highlight,
  running,
}: {
  view: InvestigationView;
  sheet: SheetWindow;
  marks: Marks;
  highlight: string | null;
  running: boolean;
}) {
  const root = useRef<HTMLDivElement>(null);
  const [boxes, setBoxes] = useState<Record<string, Box>>({});
  const [room, setRoom] = useState(0);
  const edges = useMemo(() => edgesOf(view.causal_tree), [view.causal_tree]);
  const causes = useMemo(() => new Map((view.hypotheses ?? []).map((item) => [item.cell, item])), [view.hypotheses]);
  const ratioTarget = kindOf(view.model_map, view.target?.label) === "ratio";

  useLayoutEffect(() => {
    const node = root.current;
    if (!node) return;
    const measure = () => {
      const base = node.getBoundingClientRect();
      const next: Record<string, Box> = {};
      node.querySelectorAll<HTMLElement>("[data-ref]").forEach((cell) => {
        const ref = cell.dataset.ref;
        if (!ref) return;
        const rect = cell.getBoundingClientRect();
        next[ref] = { x: rect.left - base.left, y: rect.top - base.top, w: rect.width, h: rect.height };
      });
      setBoxes(next);
      const stage = node.parentElement;
      const gutter = stage ? Number.parseFloat(getComputedStyle(stage).paddingRight) : Number.NaN;
      setRoom(base.width + (Number.isFinite(gutter) ? gutter : 0));
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(node);
    window.addEventListener("resize", measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [view.id, view.causal_tree, view.patch, view.target, sheet.sheet]);

  const wires = useMemo(() => {
    const groups = new Map<string, Edge[]>();
    edges.forEach((edge) => groups.set(edge.to, [...(groups.get(edge.to) ?? []), edge]));
    return edges.flatMap((edge, index) => {
      const from = boxes[edge.from];
      const to = boxes[edge.to];
      if (!from || !to) return [];
      const group = groups.get(edge.to) ?? [];
      const lane = group.indexOf(edge);
      const bad = edge.suspicious || marks.suspicious.has(edge.from) || marks.confirmed.has(edge.from);
      return [{ ...route({ ...edge, suspicious: bad }, from, to, lane, group.length), delay: 0.15 + index * 0.18, lane, lanes: group.length, anchor: to.y + to.h / 2, bad, edge }];
    });
  }, [edges, boxes, marks, ratioTarget]);

  const noteX = Math.min(Math.max(0, ...wires.map((wire) => wire.rail)) + 14, Math.max(0, room - NOTE_WIDTH));
  const notes: Label[] = wires
    .filter((wire) => wire.edge.depth === 0 || wire.bad)
    .map((wire) => {
      const cause = causes.get(wire.edge.from);
      const reason = reasonOf(wire.edge, cause?.claim ?? null, wire.bad ? cause?.error_type ?? null : null, ratioTarget);
      return {
        id: wire.id,
        x: noteX,
        y: wire.anchor,
        title: `${shortLabel(wire.edge.fromLabel)} ${signed(wire.edge.delta)}`,
        detail: reason.detail,
        claim: reason.claim,
        bad: wire.bad,
        delay: wire.delay,
      };
    });
  const labels = notes
    .sort((a, b) => (a.bad === b.bad ? a.y - b.y : a.bad ? -1 : 1))
    .reduce<Label[]>((stacked, note) => {
      const floor = stacked.length ? stacked[stacked.length - 1].y + 36 : note.y;
      stacked.push({ ...note, y: Math.max(note.y, floor) });
      return stacked;
    }, []);

  const patchBox = view.patch ? boxes[view.patch.cell] : undefined;
  const highlightBox = highlight ? boxes[highlight] : undefined;

  return (
    <div className={styles.stage}>
      <div className={styles.board} ref={root}>
        <SheetGrid sheet={sheet} marks={marks} title="Sheet" />
        <svg className={styles.overlay} aria-hidden="true">
          <defs>
            <marker id="arrow-up" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--accent)" />
            </marker>
            <marker id="arrow-bad" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--danger)" />
            </marker>
          </defs>
          {wires.map((wire) => (
            <g key={wire.id} className={wire.suspicious ? styles.wireBad : styles.wire} data-edge={wire.id}>
              <circle className={styles.wireDot} cx={wire.dot.x} cy={wire.dot.y} r="2.5" />
              <path d={wire.d} pathLength={1} className={`${styles.edge} ${STILL ? styles.still : ""}`} style={{ animationDelay: `${wire.delay}s` }} markerEnd={wire.suspicious ? "url(#arrow-bad)" : "url(#arrow-up)"} />
            </g>
          ))}
          {patchBox && (
            <circle
              className={styles.flash}
              cx={patchBox.x + patchBox.w / 2}
              cy={patchBox.y + patchBox.h / 2}
              r={Math.max(patchBox.w, patchBox.h) * 0.62}
              data-patch={view.patch?.cell}
            />
          )}
          {highlightBox && (
            <circle
              className={styles.highlight}
              cx={highlightBox.x + highlightBox.w / 2}
              cy={highlightBox.y + highlightBox.h / 2}
              r={Math.max(highlightBox.w, highlightBox.h) * 0.56}
              data-highlight={highlight}
            />
          )}
        </svg>
        {labels.length > 0 && (
          <div className={styles.notes} aria-hidden="true">
            {labels.map((label) => (
              <span key={label.id} className={`${styles.note} ${label.bad ? styles.noteBad : ""}`} data-wire-label={label.id} data-tone={label.bad ? "bad" : "ok"} style={{ left: label.x, top: label.y, maxWidth: NOTE_WIDTH, animationDelay: `${label.delay}s` }} title={label.claim ?? label.title}>
                <span className={styles.noteTitle}>{label.title}</span>
                {label.detail && <span className={styles.noteDetail}>{label.detail}</span>}
              </span>
            ))}
          </div>
        )}
        {running && <span className={styles.scanline} aria-hidden="true" />}
      </div>
    </div>
  );
}
