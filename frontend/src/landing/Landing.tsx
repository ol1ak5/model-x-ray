import { type ChangeEvent, useEffect, useRef } from "react";

import Brand from "../components/Brand";
import HeroSheet from "./HeroSheet";
import { Cases, Flow, Stack } from "./Sections";

export const REPOSITORY = "https://github.com/ol1ak5/model-x-ray";

function useReveal() {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const items = root.current?.querySelectorAll(".reveal") ?? [];
    if (typeof IntersectionObserver === "undefined") {
      items.forEach((item) => item.classList.add("shown"));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("shown");
          observer.unobserve(entry.target);
        }),
      { rootMargin: "0px 0px -8% 0px" },
    );
    items.forEach((item) => observer.observe(item));
    return () => observer.disconnect();
  }, []);
  return root;
}

function Actions({ onDemo, onUpload, busy, demoReady }: { onDemo: () => void; onUpload: (file: File) => void; busy: boolean; demoReady: boolean }) {
  function picked(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) onUpload(file);
  }
  return (
    <div className="cta">
      <button type="button" className="pill green" onClick={onDemo} disabled={busy || !demoReady}>
        Try the demo →
      </button>
      <input id="upload" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="visually-hidden" onChange={picked} disabled={busy} />
      <label htmlFor="upload" className="pill outline">
        {busy ? "Uploading…" : "Upload your model"}
      </label>
    </div>
  );
}

export default function Landing({ onDemo, onUpload, busy, demoReady, error }: { onDemo: () => void; onUpload: (file: File) => void; busy: boolean; demoReady: boolean; error: string | null }) {
  const root = useReveal();
  const top = () => window.scrollTo({ top: 0 });
  return (
    <div className="landing" ref={root}>
      <header className="site-nav">
        <div className="wrap">
          <Brand onHome={top} />
          <div className="nav-right">
            <nav className="nav-links" aria-label="Sections">
              <a href="#why">Did you know that?</a>
              <a href="#answer">Our answer</a>
              <a href="#how">How it works</a>
              <a href="#strengths">Strengths</a>
              <a href="#stack">Stack</a>
              <a href="#faq">FAQ</a>
            </nav>
            <button type="button" className="pill green sm" onClick={onDemo} disabled={busy || !demoReady}>
              Try the demo
            </button>
          </div>
        </div>
      </header>

      <main>
        <div className="wrap">
          <div className="hero">
            <div>
              <h1>
                Your AI agent for <em>financial model analysis.</em>
              </h1>
              <p className="lead">It detects errors, checks the logic and tests each fix, the way a financial analyst does.</p>
              <Actions onDemo={onDemo} onUpload={onUpload} busy={busy} demoReady={demoReady} />
              <p className="small">Excel .xlsx up to 4.5 MB · your file stays private</p>
              {error && (
                <p className="alert" role="alert">
                  {error}
                </p>
              )}
            </div>
            <HeroSheet />
          </div>
        </div>

        <div className="cue">
          <span>
            Do you know how much <b>one spreadsheet error</b> can cost?
          </span>
          <a href="#why" aria-label="Did you know that?">
            ↓
          </a>
        </div>

        <section id="why">
          <div className="wrap">
            <div className="heading wide reveal">
              <div className="label">Did you know that?</div>
              <h2>
                Small errors, <em>billion-dollar consequences</em>
              </h2>
            </div>
            <div className="why reveal">
              <div className="side">It has happened before</div>
              <Cases />
            </div>
          </div>
        </section>

        <section id="answer">
          <div className="wrap">
            <div className="heading reveal">
              <div className="label">Our answer</div>
              <h2>
                Nemotron reasons. <em>The engine calculates.</em>
              </h2>
            </div>
            <div className="sol reveal">
              <p>
                Language models reason well, but they <em className="red">guess numbers.</em>
              </p>
              <p>
                Model X-Ray lets NVIDIA Nemotron <em>do the reasoning</em> and a deterministic engine <em>do the maths.</em>
              </p>
              <div className="nums">
                <div>
                  <b>98%</b>
                  <span>of planted errors fixed</span>
                </div>
                <div>
                  <b>&lt;$0.05</b>
                  <span>per check on Nebius Token Factory</span>
                </div>
                <div>
                  <b>200+</b>
                  <span>financial models tested</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="how">
          <div className="wrap">
            <div className="heading reveal">
              <div className="label">How it works</div>
              <h2>
                From a workbook to <em>a verified fix</em>
              </h2>
            </div>
            <Flow />
          </div>
        </section>

        <section id="strengths">
          <div className="wrap">
            <div className="heading reveal">
              <div className="label">Strengths</div>
              <h2>
                It reviews your model <em>the way a financial analyst does</em>
              </h2>
            </div>
            <div className="grid6 reveal">
              {[
                ["Designed by a banker", "Checks what a deal team checks."],
                ["Tuned on real models", "Public valuation models by Aswath Damodaran."],
                ["Reasons and calculates", "Nemotron judges, the engine computes."],
                ["Tests every fix", "Recalculated in a copy, then challenged."],
                ["Respects your choices", "Leaves deliberate values alone."],
                ["Asks before it changes", "Your original file is never touched."],
              ].map(([title, text]) => (
                <div className="s6" key={title}>
                  <span className="ic">✓</span>
                  <div>
                    <b>{title}</b>
                    <span>{text}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="stack">
          <div className="wrap">
            <div className="heading reveal">
              <div className="label">Stack</div>
              <h2>
                Built on <em>Nebius × NVIDIA</em>
              </h2>
            </div>
            <Stack />
          </div>
        </section>

        <section id="faq">
          <div className="wrap">
            <div className="heading reveal">
              <div className="label">FAQ</div>
              <h2>
                Before you <em>upload your model</em>
              </h2>
            </div>
            <div className="faq reveal">
              {[
                ["What kind of errors does it find?", "It recalculates 50 common Excel functions and finds seven types of error: typed values, wrong references, flipped signs, incomplete ranges, wrong periods, logic errors and unusual inputs."],
                ["Will it change my file?", "No. Every fix is tested in a copy. You see the cause, the evidence and the numbers before and after, and only an approved fix is written, to a new copy."],
                ["Which files can I upload?", "Excel .xlsx files up to 4.5 MB on this demo. Your file stays private and is not kept after the check."],
                ["How much does a check cost?", "Usually one to four US cents, depending on the size of the model. In 117 runs on real workbooks, from about 50 to 6,000 formulas, the median was under one cent."],
                ["Does the AI calculate the numbers?", "No. Nemotron reasons about the formulas. Every number comes from a deterministic engine that recalculates the workbook like Excel."],
              ].map(([question, answer]) => (
                <details key={question}>
                  <summary>{question}</summary>
                  <p>{answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <div className="wrap">
          <div className="band reveal">
            <h2>
              Catch the error before it costs you.<span>Every formula, checked. Every fix, proven.</span>
            </h2>
            <div className="cta">
              <button type="button" className="pill white" onClick={onDemo} disabled={busy || !demoReady}>
                Try the demo →
              </button>
              <a className="pill ghost" href={REPOSITORY} target="_blank" rel="noreferrer">
                Read the code on GitHub
              </a>
            </div>
          </div>
        </div>
      </main>

      <footer className="site-footer">
        <div className="wrap">
          <span>Model X-Ray</span>
          <span>Powered by NVIDIA Nemotron on Nebius Token Factory</span>
        </div>
      </footer>
    </div>
  );
}
