import { useEffect, useRef, useState } from "react";

const CASES = [
  ["$6,200,000,000", "JPMorgan · 2012", "An error in its Value-at-Risk model understated the risk, and the “London Whale” trades lost $6.2 billion."],
  ["$1,300,000,000", "Fidelity Magellan · 1995", "A missing minus sign turned a $1.3 billion capital loss into a capital gain."],
  ["$11,000,000", "Kodak · 2005", "A spreadsheet error overstated a severance cost by $11 million, and two quarters were restated."],
  ["$24,000,000", "TransAlta · 2003", "A cut-and-paste error in a bid spreadsheet bought hedges at the wrong price, and the company lost C$24 million."],
];

function Amount({ text, rolling }: { text: string; rolling: boolean }) {
  const [landed, setLanded] = useState(false);
  useEffect(() => {
    setLanded(false);
    if (!rolling) return;
    let second = 0;
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => setLanded(true));
    });
    return () => {
      cancelAnimationFrame(first);
      cancelAnimationFrame(second);
    };
  }, [rolling]);
  let digit = 0;
  return (
    <b aria-label={text}>
      {[...text].map((char, index) => {
        if (!/\d/.test(char)) return <span key={index}>{char}</span>;
        const order = digit++;
        return (
          <span className="reel" key={index} aria-hidden="true">
            <i style={{ transform: landed ? "translateY(-20em)" : "translateY(0)", transition: landed ? `transform ${1.1 + order * 0.09}s cubic-bezier(.12,.75,.15,1)` : "none" }}>
              {Array.from({ length: 20 }, (_, k) => (
                <span key={k}>{k % 10}</span>
              ))}
              <span>{char}</span>
            </i>
          </span>
        );
      })}
    </b>
  );
}

export function Cases() {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setShown((current) => (current + 1) % CASES.length), 4500);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div className="cases">
      {CASES.map(([amount, who, what], index) => (
        <div className={index === shown ? "case on" : "case"} key={who} aria-hidden={index !== shown}>
          <Amount text={amount} rolling={index === shown} />
          <strong>{who}</strong>
          <span className="note">{what}</span>
        </div>
      ))}
    </div>
  );
}

const PHASES = [
  ["Read", "Opens the workbook and understands every line and period."],
  ["Investigate", "Finds the suspect cell, traces what drives it and diagnoses the cause."],
  ["Prove", "Tests the fix in a copy, tries to break it and writes the report."],
  ["Approve", "You review the evidence. Only then a corrected copy is saved."],
];

export function Flow() {
  const root = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState(-1);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    const element = root.current;
    if (!element || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setPlaying(true);
          observer.disconnect();
        }
      },
      { threshold: 0.4 },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!playing) return;
    const delay = step === -1 ? 600 : step === PHASES.length ? 3000 : 1800;
    const timer = window.setTimeout(() => setStep((current) => (current === PHASES.length ? -1 : current + 1)), delay);
    return () => window.clearTimeout(timer);
  }, [playing, step]);

  return (
    <div className="phases reveal" ref={root}>
      {PHASES.map(([name, text], index) => (
        <div className={index < step ? "phase done" : index === step ? "phase on" : "phase"} key={name}>
          <div className="c">{index + 1}</div>
          <b>{name}</b>
          <p>{text}</p>
        </div>
      ))}
    </div>
  );
}

const STACK = [
  ["Nebius Token Factory", "Inference", "Every language-model call runs here, through one OpenAI-compatible endpoint and one key."],
  ["NVIDIA Nemotron 3.5 Super", "Investigator and Verifier", "Judges each suspect cell, reviews the model's logic line by line, and tries to break every proposed fix."],
  ["Nemotron 3 Super · 3.5 Lightning", "Mapper and reporter", "3 Super labels every line and period of the workbook. Lightning writes the final report."],
  ["LangGraph", "The agent", "A ten-step state machine with a retry loop, a pause for your approval and saved checkpoints."],
  ["Calculation engine", "Our own", "Parses and recalculates the workbook like Excel: 50 functions, dependency graph, circular references."],
  ["FastAPI + React on Vercel", "The app", "A streaming API and this web app, where you upload a model and approve the fix."],
];

export function Stack() {
  const [picked, setPicked] = useState(0);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused) return;
    const timer = window.setInterval(() => setPicked((current) => (current + 1) % STACK.length), 4000);
    return () => window.clearInterval(timer);
  }, [paused]);
  const [, role, text] = STACK[picked];
  return (
    <>
      <div className="stack reveal">
        {STACK.map(([name], index) => (
          <button
            type="button"
            key={name}
            className={index === picked ? "chipbtn on" : "chipbtn"}
            aria-pressed={index === picked}
            onClick={() => setPicked(index)}
            onMouseEnter={() => {
              setPicked(index);
              setPaused(true);
            }}
            onMouseLeave={() => setPaused(false)}
          >
            {name}
          </button>
        ))}
      </div>
      <p className="stack-explain" aria-live="polite">
        <b>{role}.</b> {text}
      </p>
    </>
  );
}
