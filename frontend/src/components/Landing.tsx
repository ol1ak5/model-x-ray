import { useEffect, useRef } from "react";

import styles from "./Landing.module.css";

const STEPS = [
  { name: "Load", node: "load_sheet", text: "Reads every formula", by: "Engine" },
  { name: "Map", node: "map_model", text: "Labels lines and periods", by: "Nemotron 3 Super" },
  { name: "Locate", node: "locate", text: "Picks the cell to check", by: "Nemotron 3 Super" },
  { name: "Trace", node: "trace", text: "Follows the dependencies", by: "Engine" },
  { name: "Diagnose", node: "diagnose", text: "Judges each suspect", by: "Nemotron 3.5 Super" },
  { name: "Test", node: "test", text: "Recalculates the fix in a copy", by: "Engine" },
  { name: "Verify", node: "verify", text: "Tries to break the fix", by: "Nemotron 3.5 Super" },
  { name: "Explain", node: "explain", text: "Writes the report", by: "Nemotron 3.5 Lightning" },
  { name: "Review", node: "human_review", text: "Waits for your decision", by: "You" },
  { name: "Apply", node: "apply_fix", text: "Saves a corrected copy", by: "Engine" },
];

const STATS = [
  { value: "98%", text: "planted errors fixed (86% with rules alone)" },
  { value: "0", text: "false alarms on deliberate values" },
  { value: "200", text: "models used to develop and tune it" },
  { value: "1–3¢", text: "per full check of a model" },
];

const STRENGTHS = [
  { title: "Designed by a banker", text: "Checks what a deal team checks" },
  { title: "Tuned on real models", text: "26 Damodaran valuation models, 95 planted errors" },
  { title: "Reasons and calculates", text: "Nemotron judges, the engine computes" },
  { title: "Tests every fix", text: "Recalculated in a copy, then challenged" },
  { title: "Respects your choices", text: "Leaves deliberate values alone" },
  { title: "Asks before it changes", text: "Your original file is never touched" },
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

function Heading({ index, label, title }: { index: string; label: string; title: string }) {
  return (
    <div className={styles.heading} data-reveal>
      <p className={styles.label}>
        <span className={styles.index}>{index}</span>
        {label}
      </p>
      <h2 className={styles.title}>{title}</h2>
    </div>
  );
}

function tone(by: string): string {
  return by === "Engine" ? styles.engine : by === "You" ? styles.you : styles.nemotron;
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
      <section id="how" className={styles.section}>
        <Heading index="01" label="How it works" title="Ten steps, one agent." />
        <ol className={styles.flow}>
          {STEPS.map((step, index) => (
            <li key={step.node} className={styles.step} style={{ animationDelay: `${index * 1.2}s` }}>
              <span className={styles.stepNumber}>{index + 1}</span>
              <p className={styles.stepName}>{step.name}</p>
              <p className={styles.stepText}>{step.text}</p>
              <span className={tone(step.by)}>{step.by}</span>
            </li>
          ))}
        </ol>
        <p className={styles.loop}>↺ A rejected fix goes back to Diagnose.</p>
      </section>

      <section id="why" className={styles.section}>
        <Heading index="02" label="Why Model X-Ray" title="One broken formula can move a valuation." />
        <div className={styles.pair}>
          <article className={`${styles.card} ${styles.problem}`} data-reveal>
            <p className={styles.tag}>The problem</p>
            <p className={styles.big}>$6Bn</p>
            <p className={styles.text}>lost by JPMorgan in 2012 after an error in its Value-at-Risk model.</p>
            <ul className={styles.list}>
              <li>Errors hide in plain sight</li>
              <li>AI explains the wrong number convincingly</li>
            </ul>
          </article>
          <article className={`${styles.card} ${styles.solution}`} data-reveal>
            <p className={styles.tag}>The solution</p>
            <p className={styles.big}>Reason + recalculate</p>
            <p className={styles.text}>NVIDIA Nemotron reasons like an analyst. A deterministic engine does the maths.</p>
            <ul className={styles.list}>
              <li>Every number comes from the engine</li>
              <li>You approve every change</li>
            </ul>
          </article>
        </div>
      </section>

      <section id="strengths" className={styles.section}>
        <Heading index="03" label="Strengths" title="Built the way an analyst checks a model." />
        <div className={styles.stats} data-reveal>
          {STATS.map((stat) => (
            <div key={stat.value} className={styles.stat}>
              <p className={styles.statValue}>{stat.value}</p>
              <p className={styles.statText}>{stat.text}</p>
            </div>
          ))}
        </div>
        <ul className={styles.points} data-reveal>
          {STRENGTHS.map((item) => (
            <li key={item.title}>
              <span className={styles.check} aria-hidden="true">
                ✓
              </span>
              <span>
                <strong>{item.title}</strong>
                <span className={styles.pointText}>{item.text}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section id="stack" className={styles.section}>
        <Heading index="04" label="Stack" title="Built on Nebius × NVIDIA." />
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
          Catch the error before it costs you.
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
