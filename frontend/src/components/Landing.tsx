import { useEffect, useRef } from "react";

import styles from "./Landing.module.css";

const STATS = [
  { column: "A", value: "98%", text: "of planted errors fixed with Nemotron, against 86% with rules alone" },
  { column: "B", value: "0", text: "false alarms on deliberate values, where rules alone flagged 12 of 12" },
  { column: "C", value: "200", text: "workbooks it was developed and tuned on: 26 real valuation models and 174 synthetic deal models" },
  { column: "D", value: "1–3¢", text: "for a full check of a model on Nebius Token Factory" },
];

const STRENGTHS = [
  {
    title: "Designed by a banker",
    text: "Built by an investment banking professional. It looks for what a deal team looks for: totals that stop short, flipped signs, period slips, hard-coded numbers and lines that contradict their own label.",
  },
  {
    title: "Tuned on real models",
    text: "Developed and tuned on 26 public valuation models by Aswath Damodaran (NYU Stern) with 95 planted errors, and on 174 synthetic deal models. Part of the real models is held out for the final score.",
  },
  {
    title: "Nemotron reasons, the engine calculates",
    text: "NVIDIA Nemotron 3.5 Super judges every suspect and reviews the logic line by line. A deterministic engine recalculates every number, so no conclusion rests on a figure the model made up.",
  },
  {
    title: "Every fix is proven",
    text: "Each fix is applied to a sandbox copy and recalculated. A second Nemotron agent tries to break it, and the engine re-checks every objection before you see it.",
  },
  {
    title: "Knows a choice from a mistake",
    text: "A value a modeller typed on purpose is left alone. Rules alone flagged all 12 deliberate values in our tests; with Nemotron, none.",
  },
  {
    title: "Nothing changes without you",
    text: "You see the cell, the cause, the evidence and the numbers before and after. Approved fixes go to a new copy; the original workbook is never touched.",
  },
];

const PHASES = [
  { name: "Read", nodes: "load_sheet · map_model", text: "Opens the workbook, reads every formula and labels every line and period.", tags: ["Engine", "Nemotron 3 Super"] },
  { name: "Locate & trace", nodes: "locate · trace", text: "Picks the cell to investigate and follows the dependency graph to what drives it.", tags: ["Engine", "Nemotron 3 Super"] },
  { name: "Diagnose", nodes: "diagnose", text: "Rules propose suspects. Nemotron judges each one and reviews the logic three times, keeping what a majority finds.", tags: ["Nemotron 3.5 Super"] },
  { name: "Test & verify", nodes: "test · verify", text: "The fix is recalculated in a copy, then the Verifier tries to break it. A rejected fix goes back to diagnosis.", tags: ["Engine", "Nemotron 3.5 Super"] },
  { name: "Explain & approve", nodes: "explain · human_review · apply_fix", text: "A plain-language report checked by code, then your decision. The corrected copy is written only after you approve.", tags: ["Nemotron 3.5 Lightning", "You"] },
];

const STACK = [
  { cell: "A1", name: "Nebius Token Factory", text: "Every LLM call, through one OpenAI-compatible endpoint" },
  { cell: "B1", name: "NVIDIA Nemotron 3.5 Super", text: "The Investigator and the Verifier, with a 1M-token context" },
  { cell: "C1", name: "Nemotron 3 Super · 3.5 Lightning", text: "The model map, the locate step and the final report" },
  { cell: "D1", name: "LangGraph", text: "Ten-node state machine, retry loop, human in the loop, SQLite checkpoints" },
  { cell: "A2", name: "Calculation engine", text: "Our own: dependency graph, 50 Excel functions, circular references solved like Excel" },
  { cell: "B2", name: "FastAPI", text: "Streaming API for runs, uploads and the corrected copy" },
  { cell: "C2", name: "React + Vite", text: "This page and the investigation workspace" },
  { cell: "D2", name: "Python 3.13 + uv", text: "openpyxl reads the workbook; every test runs offline" },
];

function Heading({ formula, title, lead }: { formula: string; title: string; lead: string }) {
  return (
    <div className={styles.heading} data-reveal>
      <p className={styles.formula}>
        <span className={styles.fx}>fx</span>
        {formula}
      </p>
      <h2 className={styles.title}>{title}</h2>
      <p className={styles.lead}>{lead}</p>
    </div>
  );
}

export default function Landing() {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = root.current;
    if (!element || typeof IntersectionObserver === "undefined") return;
    element.classList.add(styles.reveal);
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          (entry.target as HTMLElement).dataset.shown = "true";
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -10% 0px" },
    );
    element.querySelectorAll("[data-reveal]").forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={root} className={styles.landing}>
      <section id="why" className={styles.section}>
        <Heading formula="=WHY()" title="One broken formula can move a valuation." lead="Financial models drive billion-dollar decisions, and the errors that matter rarely look like errors." />
        <div className={styles.pair}>
          <article className={`${styles.card} ${styles.problem}`} data-reveal>
            <p className={styles.tag}>The problem</p>
            <p className={styles.big}>$6Bn</p>
            <p className={styles.caption}>JPMorgan, “London Whale”, 2012</p>
            <p className={styles.text}>An error in the bank’s Value-at-Risk model understated its risk exposure. The trading losses reached about six billion dollars.</p>
            <ul className={styles.list}>
              <li>Errors hide in plain sight: a typed number where a formula should be, a sum one row short, a sign flipped in one year.</li>
              <li>AI looks like the obvious reviewer, but language models struggle with numbers and explain the wrong one convincingly.</li>
            </ul>
          </article>
          <article className={`${styles.card} ${styles.solution}`} data-reveal>
            <p className={styles.tag}>The solution</p>
            <p className={styles.big}>Reason + recalculate</p>
            <p className={styles.caption}>NVIDIA Nemotron with a deterministic engine</p>
            <p className={styles.text}>Model X-Ray works the way an experienced analyst does: judgement from the model, numbers from a tool that cannot guess.</p>
            <ul className={styles.list}>
              <li>Nemotron reads every formula, tells real errors from deliberate choices and proposes the fix.</li>
              <li>The engine maps every dependency and recalculates every value, so each conclusion rests on verifiable numbers.</li>
              <li>You see the evidence and approve the change. The original workbook never changes.</li>
            </ul>
          </article>
        </div>
      </section>

      <section id="strengths" className={styles.section}>
        <Heading formula="=STRENGTHS()" title="Built the way an analyst checks a model." lead="Designed by an investment banking professional, developed and tuned on real valuation models, and measured on errors with known answers." />
        <div className={styles.sheet} role="table" aria-label="Results" data-reveal>
          <div className={styles.sheetRow} role="row">
            <span className={styles.corner} role="columnheader" />
            {STATS.map((stat) => (
              <span key={stat.column} className={styles.columnHead} role="columnheader">
                {stat.column}
              </span>
            ))}
          </div>
          <div className={styles.sheetRow} role="row">
            <span className={styles.rowHead} role="rowheader">
              1
            </span>
            {STATS.map((stat) => (
              <div key={stat.column} className={styles.stat} role="cell">
                <p className={styles.statValue}>{stat.value}</p>
                <p className={styles.statText}>{stat.text}</p>
              </div>
            ))}
          </div>
        </div>
        <div className={styles.grid}>
          {STRENGTHS.map((item, index) => (
            <article key={item.title} className={styles.card} data-reveal style={{ transitionDelay: `${(index % 3) * 80}ms` }}>
              <span className={styles.number}>{String(index + 1).padStart(2, "0")}</span>
              <h3 className={styles.cardTitle}>{item.title}</h3>
              <p className={styles.text}>{item.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="how" className={styles.section}>
        <Heading formula="=HOW()" title="Ten steps, one state machine." lead="A LangGraph agent. Each step uses the Nemotron model that fits its job, and every step that computes uses the engine and no model at all." />
        <ol className={styles.phases}>
          {PHASES.map((phase, index) => (
            <li key={phase.name} className={styles.phase} data-reveal style={{ transitionDelay: `${index * 90}ms` }}>
              <span className={styles.phaseDot}>{index + 1}</span>
              <h3 className={styles.cardTitle}>{phase.name}</h3>
              <p className={styles.nodes}>{phase.nodes}</p>
              <p className={styles.text}>{phase.text}</p>
              <p className={styles.tags}>
                {phase.tags.map((tag) => (
                  <span key={tag} className={tag === "Engine" ? styles.engine : tag === "You" ? styles.you : styles.nemotron}>
                    {tag}
                  </span>
                ))}
              </p>
            </li>
          ))}
        </ol>
        <p className={styles.loop} data-reveal>
          ↺ A fix the Verifier rejects goes back to diagnosis, and you can edit any fix and test it again.
        </p>
      </section>

      <section id="stack" className={styles.section}>
        <Heading formula="=STACK()" title="Built on Nebius × NVIDIA." lead="One OpenAI-compatible endpoint, five Nemotron models, and a calculation engine that speaks Excel." />
        <div className={styles.stack}>
          {STACK.map((item, index) => (
            <article key={item.name} className={styles.tile} data-reveal style={{ transitionDelay: `${(index % 4) * 70}ms` }}>
              <span className={styles.cell}>{item.cell}</span>
              <h3 className={styles.tileName}>{item.name}</h3>
              <p className={styles.text}>{item.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.closing} data-reveal>
        <h2 className={styles.closingTitle}>
          Check the model before the committee does.
          <span>Every formula, checked. Every fix, proven.</span>
        </h2>
        <div className={styles.closingActions}>
          <a className={styles.light} href="#top">
            Try it on the demo model ↑
          </a>
          <a className={styles.outline} href="https://github.com/ol1ak5/model-x-ray" target="_blank" rel="noreferrer">
            Read the code on GitHub
          </a>
        </div>
      </section>
    </div>
  );
}
