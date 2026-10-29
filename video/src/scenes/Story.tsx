import { AbsoluteFill, random, useCurrentFrame } from "remotion";
import { C, FONT, MONO } from "../theme";
import type { Scene } from "../timeline";
import { Fade, Rise, Roll, Wave, Words, clamp, ease, useSpring } from "../parts";

const COLS = 21;
const ROWS = 31;
const CW = 150;
const CH = 46;
const HOT = { col: 10, row: 15 };

function cellValue(col: number, row: number): string {
  const r = random(`cell-${col}-${row}`);
  if (col === 0) return ["Revenue", "COGS", "Gross profit", "Opex", "EBITDA", "D&A", "EBIT", "Interest", "Tax", "Net income", "Capex", "FCF"][row % 12];
  if (r < 0.12) return "";
  const n = (r * 9000 - 1500).toFixed(1);
  return Number(n) < 0 ? `(${Math.abs(Number(n)).toFixed(1)})` : n;
}

export function Open({ scene }: { scene: Scene }) {
  const frame = useCurrentFrame();
  const two = scene.lines[1];
  const typed = "285.76".slice(0, Math.max(0, Math.floor((frame - 10) / 4)));
  const zoom = clamp(frame, two.start - 6, two.start + 50, 0, 1, ease);
  const scale = 7 - 6.25 * zoom;
  const others = clamp(frame, two.start - 2, two.start + 30);
  const hotPulse = 0.5 + 0.5 * Math.sin(frame / 5);
  const gridW = COLS * CW;
  const gridH = ROWS * CH;
  const hx = HOT.col * CW + CW / 2;
  const hy = HOT.row * CH + CH / 2;
  const red = clamp(frame, two.start + 40, two.start + 55);
  return (
    <AbsoluteFill style={{ background: C.night, overflow: "hidden" }}>
      <div style={{ position: "absolute", left: 960 - hx, top: 540 - hy, width: gridW, height: gridH, transform: `scale(${scale})`, transformOrigin: `${hx}px ${hy}px` }}>
        {Array.from({ length: ROWS }, (_, row) =>
          Array.from({ length: COLS }, (_, col) => {
            const hot = col === HOT.col && row === HOT.row;
            const near = Math.hypot(col - HOT.col, (row - HOT.row) * 0.6);
            const appear = clamp(others, near / 14 - 0.1, near / 14 + 0.2);
            return (
              <div
                key={`${col}-${row}`}
                style={{
                  position: "absolute",
                  left: col * CW,
                  top: row * CH,
                  width: CW,
                  height: CH,
                  boxSizing: "border-box",
                  border: `1px solid rgba(255,255,255,${hot ? 0 : 0.08 * appear})`,
                  fontFamily: col === 0 ? FONT : MONO,
                  fontSize: 17,
                  color: `rgba(255,255,255,${hot ? 1 : 0.35 * appear})`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: col === 0 ? "flex-start" : "flex-end",
                  padding: "0 12px",
                  ...(hot
                    ? {
                        border: `2px solid ${red > 0 ? `rgba(194,47,47,${0.6 + 0.4 * hotPulse * red})` : C.bright}`,
                        background: red > 0 ? `rgba(194,47,47,${0.25 * red})` : "rgba(74,222,128,0.08)",
                        boxShadow: red > 0 ? `0 0 ${30 * hotPulse * red}px rgba(194,47,47,0.7)` : "0 0 24px rgba(74,222,128,0.25)",
                        zIndex: 2,
                      }
                    : {}),
                }}
              >
                {hot ? (
                  <span>
                    {typed}
                    <span style={{ opacity: frame % 30 < 15 && frame < two.start ? 1 : 0, color: C.bright }}>|</span>
                  </span>
                ) : (
                  cellValue(col, row)
                )}
              </div>
            );
          }),
        )}
      </div>
      <AbsoluteFill style={{ background: `radial-gradient(900px 600px at 50% 50%, transparent 40%, ${C.night} 100%)`, opacity: others }} />
    </AbsoluteFill>
  );
}

const CASES = [
  { amount: "$6,200,000,000", who: "JPMorgan · 2012", what: "One formula divided by the wrong number." },
  { amount: "$1,300,000,000", who: "Fidelity Magellan · 1995", what: "A capital loss reported as a capital gain." },
];

export function Stakes({ scene }: { scene: Scene }) {
  const frame = useCurrentFrame();
  const [l1, l2, l3] = scene.lines;
  const starts = [l1.start, l2.start];
  const ends = [l2.start, l3.start];
  const outro = clamp(frame, l3.start, l3.start + 18);
  return (
    <AbsoluteFill style={{ background: C.night, color: "#fff", fontFamily: FONT }}>
      <Wave strength={0.5} tint="74, 222, 128" />
      {CASES.map((item, index) => {
        const inP = clamp(frame, starts[index] - 4, starts[index] + 14);
        const outP = clamp(frame, ends[index] - 6, ends[index] + 8);
        if (inP === 0 || outP === 1) return null;
        return (
          <AbsoluteFill key={item.who} style={{ justifyContent: "center", paddingLeft: 160, opacity: inP * (1 - outP), transform: `translateY(${-outP * 120}px) scale(${1 - outP * 0.1})`, filter: `blur(${outP * 14}px)` }}>
            <div style={{ fontSize: 30, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color: C.bright, marginBottom: 26 }}>{item.who}</div>
            <Roll value={item.amount} at={starts[index]} size={180} />
            <div style={{ marginTop: 40, fontSize: 52, fontWeight: 500, color: "rgba(255,255,255,0.75)", letterSpacing: "-0.02em" }}>
              <Words text={item.what} at={starts[index] + 18} every={3} />
            </div>
          </AbsoluteFill>
        );
      })}
      {frame >= l3.start - 2 && (
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity: outro }}>
          <div style={{ display: "flex", gap: 70, marginBottom: 70, fontSize: 44, fontWeight: 700, color: "rgba(255,255,255,0.4)", fontVariantNumeric: "tabular-nums" }}>
            {["$6.2B", "$1.3B", "$24M", "$11M"].map((amount, index) => (
              <Rise key={amount} at={l3.start + index * 4} distance={30}>
                <span>{amount}</span>
              </Rise>
            ))}
          </div>
          <div style={{ fontSize: 120, fontWeight: 800, letterSpacing: "-0.045em", lineHeight: 1 }}>
            <Words text="One cell." at={l3.start + 12} every={5} />
            <Words text="Real money." at={l3.start + 26} every={5} color={() => C.red} />
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
}

const TEAMS = ["Financial analysts", "FP&A", "Corporate finance", "M&A", "Investment banking", "Valuation", "Deal advisory", "Auditors"];
const OTHERS = ["Researchers", "Students", "Founders", "Business owners"];
const FUNCS = ["XLOOKUP", "SUMIFS", "NPV", "IRR", "OFFSET", "INDEX", "MATCH", "SUMPRODUCT", "XNPV", "XIRR", "PMT", "IFERROR", "COUNTIFS", "EOMONTH", "VLOOKUP", "ROUND", "RANK", "CHOOSE", "EDATE", "HLOOKUP"];

export function Who({ scene }: { scene: Scene }) {
  const frame = useCurrentFrame();
  const [l1, l2, l3] = scene.lines;
  const step = l1.frames / (TEAMS.length + 1);
  return (
    <AbsoluteFill style={{ background: "#fff", fontFamily: FONT, color: C.ink }}>
      <Wave />
      <Fade from={0} to={l2.start - 6} style={{ position: "absolute", inset: 0 }}>
        <AbsoluteFill style={{ justifyContent: "center", padding: "0 140px" }}>
          <Rise at={l1.start - 6} distance={20}>
            <div style={{ fontSize: 26, fontWeight: 600, letterSpacing: "0.16em", textTransform: "uppercase", color: C.g3, marginBottom: 34 }}>Built for</div>
          </Rise>
          <div style={{ display: "flex", flexWrap: "wrap", columnGap: 44, rowGap: 6, fontSize: 92, fontWeight: 800, letterSpacing: "-0.045em", lineHeight: 1.08 }}>
            {TEAMS.map((team, index) => {
              const at = l1.start + index * step;
              const s = clamp(frame, at, at + 14);
              const active = frame >= at && frame < at + step + 4;
              return (
                <span key={team} style={{ opacity: s, transform: `translateY(${(1 - s) * 50}px) scale(${0.9 + 0.1 * s})`, color: active ? C.g3 : index % 2 ? C.ink : "#2b322d", filter: `blur(${(1 - s) * 10}px)` }}>
                  {team}
                </span>
              );
            })}
          </div>
        </AbsoluteFill>
      </Fade>
      <Fade from={l2.start - 2} to={l3.start - 4} style={{ position: "absolute", inset: 0 }}>
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
          <div style={{ display: "flex", gap: 56, fontSize: 54, fontWeight: 600, color: C.muted, marginBottom: 60 }}>
            {OTHERS.map((name, index) => (
              <Rise key={name} at={l2.start + index * 6} distance={40}>
                <span>{name}</span>
              </Rise>
            ))}
          </div>
          <div style={{ fontSize: 120, fontWeight: 800, letterSpacing: "-0.05em", textAlign: "center", lineHeight: 1.02 }}>
            <Words text="If you work in Excel," at={l2.start + Math.round(l2.frames * 0.5)} every={4} color={(word) => (word.startsWith("Excel") ? C.g3 : undefined)} />
            <br />
            <Words text="it works for you." at={l2.start + Math.round(l2.frames * 0.5) + 20} every={4} />
          </div>
        </AbsoluteFill>
      </Fade>
      {frame >= l3.start - 4 && (
        <AbsoluteFill>
          {Array.from({ length: 7 }, (_, row) => {
            const dir = row % 2 ? -1 : 1;
            const shift = ((frame - l3.start) * (6 + row * 1.7) * dir) % 1600;
            const vis = clamp(frame, l3.start - 4, l3.start + 20);
            return (
              <div key={row} style={{ position: "absolute", top: 70 + row * 140, left: -400 + shift, whiteSpace: "nowrap", fontFamily: MONO, fontSize: 40 + (row % 3) * 10, color: row === 3 ? "transparent" : `rgba(18,129,74,${0.12 + (row % 3) * 0.05})`, opacity: vis }}>
                {Array.from({ length: 4 }, () => FUNCS.slice(row * 3).concat(FUNCS.slice(0, row * 3)).map((f) => `${f}( )`).join("   ")).join("   ")}
              </div>
            );
          })}
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
            <div style={{ background: "radial-gradient(ellipse 50% 50% at 50% 50%, rgba(255,255,255,1) 55%, rgba(255,255,255,0) 100%)", padding: "110px 220px", textAlign: "center" }}>
              <div style={{ fontSize: 96, fontWeight: 800, letterSpacing: "-0.045em", lineHeight: 1.05 }}>
                <Words text="Thousands of formulas." at={l3.start} every={4} />
                <br />
                <Words text="Dozens of tabs." at={l3.start + 26} every={4} />
              </div>
              <Rise at={l3.start + 48} distance={30}>
                <div style={{ marginTop: 30, fontSize: 30, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: C.g3 }}>52 Excel functions understood</div>
              </Rise>
            </div>
          </AbsoluteFill>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
}

const CLAIM = "EBITDA grew 12% in 2027. Gross profit margin reached ";

export function Ai({ scene }: { scene: Scene }) {
  const frame = useCurrentFrame();
  const [l1, l2, l3] = scene.lines;
  const chars = Math.floor(clamp(frame, l1.start, l1.start + l1.frames - 8, 0, CLAIM.length + 5, (t) => t));
  const shown = CLAIM.slice(0, chars);
  const number = chars > CLAIM.length ? "47.5%" : "";
  const wrong = clamp(frame, l2.start, l2.start + 10);
  const glitch = frame >= l2.start && frame < l2.start + 14 ? (frame % 3) - 1 : 0;
  const enter = useSpring(l1.start - 8);
  const leave = clamp(frame, l3.start - 6, l3.start + 10);
  return (
    <AbsoluteFill style={{ background: "#fff", fontFamily: FONT, color: C.ink }}>
      <Wave strength={0.7} />
      <AbsoluteFill style={{ opacity: 1 - leave, filter: `blur(${leave * 12}px)` }}>
        <div style={{ position: "absolute", left: 140, top: 270, width: 820, transform: `translateY(${(1 - enter) * 80}px)`, opacity: enter }}>
          <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color: C.faint, marginBottom: 18 }}>A chatbot says</div>
          <div style={{ background: C.soft, border: `1px solid ${C.line}`, borderRadius: 28, padding: "40px 46px", fontSize: 44, lineHeight: 1.35, fontWeight: 500, minHeight: 250 }}>
            {shown}
            <span style={{ position: "relative", display: "inline-block", color: wrong ? C.red : C.ink, transform: `translateX(${glitch * 6}px)`, fontWeight: 700 }}>
              {number}
              <span style={{ position: "absolute", left: -4, right: -4, top: "52%", height: 5, background: C.red, transform: `scaleX(${wrong})`, transformOrigin: "left" }} />
            </span>
            {chars <= CLAIM.length + 4 && <span style={{ color: C.g3 }}>▍</span>}
          </div>
          <Rise at={l2.start + 12} distance={20}>
            <div style={{ marginTop: 22, fontFamily: MONO, fontSize: 30, color: C.red }}>Recalculated: 97.2 / 216.0 = 45.0%</div>
          </Rise>
        </div>
        <div style={{ position: "absolute", left: 1060, top: 330, fontSize: 84, fontWeight: 800, letterSpacing: "-0.045em", lineHeight: 1.08 }}>
          <Words text="Built to reason." at={l2.start + 6} every={4} />
          <br />
          <Words text="Not to calculate." at={l2.start + 34} every={4} color={() => C.red} />
        </div>
      </AbsoluteFill>
      {frame >= l3.start - 4 && (
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 80, fontSize: 170, fontWeight: 800, letterSpacing: "-0.055em" }}>
            <Rise at={l3.start} distance={50}>
              <span style={{ position: "relative", color: C.faint }}>
                Plausible
                <span style={{ position: "absolute", left: -6, right: -6, top: "55%", height: 10, background: C.ink, transform: `scaleX(${clamp(frame, l3.start + Math.round(l3.frames * 0.45), l3.start + Math.round(l3.frames * 0.45) + 12)})`, transformOrigin: "left" }} />
              </span>
            </Rise>
            <Rise at={l3.start + Math.round(l3.frames * 0.55)} distance={50}>
              <span style={{ color: C.g3 }}>Proven.</span>
            </Rise>
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
}
