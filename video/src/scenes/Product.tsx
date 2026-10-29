import { useContext } from "react";
import { AbsoluteFill, Easing, Img, interpolate, random, staticFile, useCurrentFrame } from "remotion";
import { BAND, C, FONT, MONO } from "../theme";
import type { Scene } from "../timeline";
import { Brand, CameraStyle, Fade, Logo, Rise, Wave, Words, clamp, useSpring } from "../parts";

export function Reveal({ scene }: { scene: Scene }) {
  const frame = useCurrentFrame();
  const [l1, l2] = scene.lines;
  const band = clamp(frame, l1.start - 16, l1.start + 10);
  const draw = clamp(frame, l1.start - 14, l1.start + 26);
  const pop = useSpring(l1.start - 4, 14, 120);
  const flash = clamp(frame, l1.start - 16, l1.start - 6) * (1 - clamp(frame, l1.start - 6, l1.start + 14));
  return (
    <AbsoluteFill style={{ background: C.night, fontFamily: FONT }}>
      <AbsoluteFill style={{ background: BAND, opacity: band }} />
      <div style={{ opacity: band }}>
        <Wave strength={0.9} tint="255, 255, 255" speed={0.02} />
      </div>
      <AbsoluteFill style={{ background: "#fff", opacity: flash * 0.5 }} />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", color: "#fff" }}>
        <div style={{ transform: `scale(${0.6 + 0.4 * pop})`, marginBottom: 40 }}>
          <Logo size={190} draw={draw} />
        </div>
        <div style={{ fontSize: 150, fontWeight: 800, letterSpacing: "-0.05em", lineHeight: 1, display: "flex", gap: 34 }}>
          <Rise at={l1.start + 2} distance={60}>
            <span>Model</span>
          </Rise>
          <Rise at={l1.start + 10} distance={60}>
            <span style={{ color: C.bright }}>X-Ray</span>
          </Rise>
        </div>
        <div style={{ marginTop: 44, fontSize: 56, fontWeight: 500, color: "rgba(255,255,255,0.86)", letterSpacing: "-0.02em" }}>
          <Words text="The debugger for financial models." at={l2.start} every={4} />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
}

type Cam = { t: number; x: number; y: number; z: number };
type Shot = { src: string; from: number; to: number; cams: Cam[]; dip?: boolean };

const smooth = Easing.inOut(Easing.sin);

const FW = 1400;
const FH = 875;

function camAt(cams: Cam[], t: number): Cam {
  if (t <= cams[0].t) return cams[0];
  for (let i = 1; i < cams.length; i++) {
    if (t <= cams[i].t) {
      const a = cams[i - 1];
      const b = cams[i];
      const p = smooth((t - a.t) / (b.t - a.t));
      return { t, x: a.x + (b.x - a.x) * p, y: a.y + (b.y - a.y) * p, z: a.z + (b.z - a.z) * p };
    }
  }
  return cams[cams.length - 1];
}

function Screen({ shot, frame }: { shot: Shot; frame: number }) {
  const cam = camAt(shot.cams, frame);
  const fadeIn = shot.dip ? clamp(frame, shot.from + 2, shot.from + 12, 0, 1, smooth) : clamp(frame, shot.from - 7, shot.from + 7, 0, 1, smooth);
  const fadeOut = shot.src === "landing" ? clamp(frame, shot.to - 8, shot.to + 2, 1, 0, smooth) : clamp(frame, shot.to + 7, shot.to + 9, 1, 0);
  const cx = Math.min(Math.max(cam.x, 0.5 / cam.z), 1 - 0.5 / cam.z);
  const cy = Math.min(Math.max(cam.y, 0.5 / cam.z), 1 - 0.5 / cam.z);
  return (
    <div style={{ position: "absolute", inset: 0, opacity: Math.min(fadeIn, fadeOut) }}>
      <Img
        src={staticFile(`demo/${shot.src}.png`)}
        style={{ position: "absolute", width: FW, height: FH, left: 0, top: 0, transformOrigin: "0 0", transform: `translate(${FW / 2 - cx * FW * cam.z}px, ${FH / 2 - cy * FH * cam.z}px) scale(${cam.z})` }}
      />
    </div>
  );
}

type Spot = { t: number; x: number; y: number; w: number; h: number };

function spotAt(spots: Spot[], t: number): Spot {
  if (t <= spots[0].t) return spots[0];
  for (let i = 1; i < spots.length; i++) {
    const a = spots[i - 1];
    const b = spots[i];
    const start = b.t - 22;
    if (t < start) return a;
    if (t <= b.t) {
      const p = smooth((t - start) / 22);
      return { t, x: a.x + (b.x - a.x) * p, y: a.y + (b.y - a.y) * p, w: a.w + (b.w - a.w) * p, h: a.h + (b.h - a.h) * p };
    }
  }
  return spots[spots.length - 1];
}

function Spotlight({ spots, cam, frame, end }: { spots: Spot[]; cam: Cam; frame: number; end: number }) {
  const s = spotAt(spots, frame);
  const on = Math.min(clamp(frame, spots[0].t - 10, spots[0].t + 8, 0, 1, smooth), clamp(frame, end - 40, end - 20, 1, 0, smooth));
  const left = FW / 2 + (s.x - cam.x) * FW * cam.z;
  const top = FH / 2 + (s.y - cam.y) * FH * cam.z;
  return (
    <div
      style={{
        position: "absolute",
        left,
        top,
        width: s.w * FW * cam.z,
        height: s.h * FH * cam.z,
        borderRadius: 14,
        border: `2px solid rgba(18, 129, 74, ${0.9 * on})`,
        boxShadow: `0 0 0 3000px rgba(12, 22, 16, ${0.3 * on}), 0 0 40px rgba(74, 222, 128, ${0.35 * on})`,
      }}
    />
  );
}

function Note({ at, until, kicker, text }: { at: number; until: number; kicker: string; text: string }) {
  const frame = useCurrentFrame();
  const p = clamp(frame, at, at + 16);
  const q = clamp(frame, until - 8, until + 4, 1, 0);
  if (p === 0 || q === 0) return null;
  return (
    <div style={{ position: "absolute", left: 0, top: 0, opacity: Math.min(p, q), transform: `translateX(${(1 - p) * 40}px)`, filter: `blur(${(1 - Math.min(p, q)) * 8}px)` }}>
      <div style={{ width: 54 * p, height: 3, background: C.g3, marginBottom: 22 }} />
      <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: "0.16em", textTransform: "uppercase", color: C.g3, marginBottom: 14 }}>{kicker}</div>
      <div style={{ fontSize: 46, fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1.12, color: C.ink }}>{text}</div>
    </div>
  );
}

export function Demo({ scene }: { scene: Scene }) {
  const frame = useCurrentFrame();
  const L = scene.lines;
  const mid = (i: number, k: number) => L[i].start + Math.round(L[i].frames * k);
  const click = L[1].start - 6;
  const style = useContext(CameraStyle);
  const drift: Cam[] = [
    { t: L[1].start, x: 0.5, y: 0.5, z: 1.0 },
    { t: scene.duration, x: 0.5, y: 0.5, z: 1.07 },
  ];
  const spots: Spot[] = [
    { t: L[1].start + 14, x: 0.06, y: 0.27, w: 0.26, h: 0.52 },
    { t: mid(3, 0.6), x: 0.06, y: 0.27, w: 0.26, h: 0.52 },
    { t: L[4].start, x: 0.255, y: 0.27, w: 0.685, h: 0.28 },
    { t: L[5].start, x: 0.34, y: 0.415, w: 0.6, h: 0.32 },
    { t: L[6].start, x: 0.34, y: 0.83, w: 0.6, h: 0.16 },
    { t: mid(7, 0.3), x: 0.255, y: 0.33, w: 0.685, h: 0.34 },
  ];
  const path: Cam[] = [
    { t: L[1].start, x: 0.5, y: 0.45, z: 1.08 },
    { t: mid(1, 0.7), x: 0.32, y: 0.6, z: 1.38 },
    { t: mid(3, 0.55), x: 0.32, y: 0.6, z: 1.42 },
    { t: L[4].start, x: 0.58, y: 0.56, z: 1.42 },
    { t: L[5].start, x: 0.59, y: 0.54, z: 1.45 },
    { t: mid(5, 0.75), x: 0.6, y: 0.6, z: 1.48 },
    { t: L[7].start, x: 0.6, y: 0.8, z: 1.48 },
    { t: mid(7, 0.45), x: 0.55, y: 0.6, z: 1.3 },
    { t: scene.duration, x: 0.5, y: 0.5, z: 1.04 },
  ];
  const shots: Shot[] = [
    { src: "landing", from: 0, to: L[1].start, cams: [{ t: 0, x: 0.5, y: 0.5, z: 1 }, { t: mid(0, 0.4), x: 0.42, y: 0.42, z: 1.12 }, { t: click, x: 0.25, y: 0.5, z: 1.5 }] },
    { src: "run-read", from: L[1].start, to: mid(1, 0.55), cams: style === "spotlight" ? drift : path, dip: true },
    { src: "run-investigate", from: mid(1, 0.55), to: L[3].start, cams: style === "spotlight" ? drift : path },
    { src: "run-prove", from: L[3].start, to: mid(3, 0.65), cams: style === "spotlight" ? drift : path },
    { src: "run-first", from: mid(3, 0.65), to: L[4].start, cams: style === "spotlight" ? drift : path },
    { src: "run-found", from: L[4].start, to: L[5].start, cams: style === "spotlight" ? drift : path },
    { src: "error-open", from: L[5].start, to: L[6].start, cams: style === "spotlight" ? drift : path },
    { src: "ask", from: L[6].start, to: L[7].start, cams: style === "spotlight" ? drift : path },
    { src: "approving", from: L[7].start, to: mid(7, 0.3), cams: style === "spotlight" ? drift : path },
    { src: "fixed", from: mid(7, 0.3), to: scene.duration + 10, cams: style === "spotlight" ? drift : path },
  ];
  const enter = useSpring(0, 16, 60);
  const sway = Math.sin(frame / 70) * 1.5;
  const cursorIn = clamp(frame, mid(0, 0.55), click - 4);
  const press = frame >= click - 4 && frame < click + 2 ? 0.8 : 1;
  const ring = clamp(frame, click - 2, click + 14);
  const landing = camAt(shots[0].cams, frame);
  const bx = 0.135;
  const by = 0.56;
  const sx = FW / 2 + (bx - Math.min(Math.max(landing.x, 0.5 / landing.z), 1 - 0.5 / landing.z)) * FW * landing.z;
  const sy = FH / 2 + (by - Math.min(Math.max(landing.y, 0.5 / landing.z), 1 - 0.5 / landing.z)) * FH * landing.z;
  const cx = interpolate(cursorIn, [0, 1], [FW * 0.7, sx]);
  const cy = interpolate(cursorIn, [0, 1], [FH * 0.9, sy]);
  const notes = [
    { kicker: "Live demo", text: "A PPA model with 2,400 formulas and 3 planted errors" },
    { kicker: "01 · Read", text: "Nemotron 3 Super labels every line and period" },
    { kicker: "02 · Investigate", text: "Nemotron 3.5 Super judges every suspect" },
    { kicker: "03 · Prove", text: "Fixed in a copy, recalculated, challenged" },
    { kicker: "Result", text: "3 planted errors, 3 found" },
    { kicker: "Evidence", text: "The cell, the cause, the fix and the proof" },
    { kicker: "Ask", text: "It answers questions about its own finding" },
    { kicker: "You decide", text: "Approve, edit or reject. The original never changes" },
  ];
  return (
    <AbsoluteFill style={{ background: "#fff", fontFamily: FONT }}>
      <Wave strength={0.8} />
      <div style={{ position: "absolute", left: 70, top: 92, width: FW, height: FH + 44, perspective: 2400 }}>
        <div
          style={{
            width: "100%",
            height: "100%",
            transform: `rotateY(${(1 - enter) * 28 + sway}deg) rotateX(${(1 - enter) * 12}deg) scale(${0.82 + 0.18 * enter}) translateY(${(1 - enter) * 120}px)`,
            transformOrigin: "60% 50%",
            borderRadius: 18,
            overflow: "hidden",
            boxShadow: "0 40px 120px rgba(10, 74, 41, 0.22), 0 0 0 1px rgba(17, 21, 18, 0.08)",
            background: "#fff",
            opacity: enter,
          }}
        >
          <div style={{ height: 44, background: C.soft, borderBottom: `1px solid ${C.line}`, display: "flex", alignItems: "center", padding: "0 18px", gap: 9 }}>
            {["#ff5f57", "#febc2e", "#28c840"].map((color) => (
              <span key={color} style={{ width: 13, height: 13, borderRadius: 7, background: color }} />
            ))}
            <div style={{ marginLeft: 22, fontFamily: MONO, fontSize: 17, color: C.muted }}>model-x-ray.vercel.app</div>
          </div>
          <div style={{ position: "relative", width: FW, height: FH, overflow: "hidden" }}>
            {shots.map((shot) => (frame >= shot.from - 10 && frame <= shot.to + 10 ? <Screen key={shot.src} shot={shot} frame={frame} /> : null))}
            {style === "spotlight" && frame >= L[1].start && <Spotlight spots={spots} cam={camAt(drift, frame)} frame={frame} end={scene.duration} />}
            {frame < L[1].start + 4 && cursorIn > 0 && (
              <div style={{ position: "absolute", left: cx, top: cy, transform: `scale(${press})`, transformOrigin: "0 0", opacity: clamp(frame, L[1].start - 2, L[1].start + 4, 1, 0) }}>
                <div style={{ position: "absolute", left: -40, top: -40, width: 80, height: 80, borderRadius: 40, border: `3px solid ${C.g3}`, opacity: ring > 0 && ring < 1 ? 1 - ring : 0, transform: `scale(${0.3 + ring})` }} />
                <svg width="40" height="40" viewBox="0 0 24 24">
                  <path d="M4 2l15 10-7 1.5L8.5 21z" fill={C.ink} stroke="#fff" strokeWidth="1.4" strokeLinejoin="round" />
                </svg>
              </div>
            )}
          </div>
        </div>
      </div>
      <div style={{ position: "absolute", left: 1510, top: 380, width: 360 }}>
        {notes.map((note, index) => (
          <Note key={note.kicker} at={L[index].start - 4} until={index < 7 ? L[index + 1].start - 2 : scene.duration} kicker={note.kicker} text={note.text} />
        ))}
      </div>
    </AbsoluteFill>
  );
}

function Network({ frame, at }: { frame: number; at: number }) {
  const nodes = Array.from({ length: 26 }, (_, i) => ({ x: 120 + random(`nx${i}`) * 560, y: 140 + random(`ny${i}`) * 430 }));
  const edges: [number, number][] = [];
  nodes.forEach((a, i) => nodes.forEach((b, j) => j > i && Math.hypot(a.x - b.x, a.y - b.y) < 150 && edges.push([i, j])));
  const grow = clamp(frame, at, at + 40);
  return (
    <svg width={800} height={700}>
      {edges.map(([i, j], k) => {
        const pulse = 0.25 + 0.75 * Math.max(0, Math.sin(frame / 9 + k * 0.7));
        return <line key={k} x1={nodes[i].x} y1={nodes[i].y} x2={nodes[i].x + (nodes[j].x - nodes[i].x) * grow} y2={nodes[i].y + (nodes[j].y - nodes[i].y) * grow} stroke={C.bright} strokeOpacity={0.15 + 0.35 * pulse} strokeWidth={1.4} />;
      })}
      {nodes.map((n, i) => (
        <circle key={i} cx={n.x} cy={n.y} r={(4 + 3 * Math.max(0, Math.sin(frame / 7 + i))) * grow} fill={C.bright} fillOpacity={0.8} />
      ))}
    </svg>
  );
}

function Calc({ frame, at }: { frame: number; at: number }) {
  const rows = ["Revenue", "COGS", "Gross profit", "Opex", "EBITDA"];
  const base = [185.2, -101.9, 83.3, -47.6, 35.7];
  const t = Math.max(0, frame - at);
  return (
    <div style={{ fontFamily: MONO, fontSize: 30, color: "#fff", width: 560 }}>
      {rows.map((row, i) => {
        const tick = Math.floor(t / 6 + i * 2);
        const value = base[i] + (i === 2 || i === 4 ? Math.sin(tick) * 0.4 : 0);
        const hl = tick % rows.length === i;
        return (
          <div key={row} style={{ display: "flex", justifyContent: "space-between", padding: "16px 4px", borderBottom: "1px solid rgba(255,255,255,0.12)", color: hl ? C.bright : "rgba(255,255,255,0.8)", opacity: clamp(frame, at + i * 4, at + i * 4 + 12) }}>
            <span style={{ fontFamily: FONT }}>{row}</span>
            <span>{value < 0 ? `(${Math.abs(value).toFixed(1)})` : value.toFixed(1)}</span>
          </div>
        );
      })}
      <div style={{ marginTop: 22, fontSize: 24, color: "rgba(255,255,255,0.5)" }}>=D4+D5 · recalculated {Math.floor(t * 37) % 2400} / 2,400</div>
    </div>
  );
}

const MODELS = [
  { name: "Nemotron 3.5 Super", job: "The Investigator judges every suspect. The Verifier tries to break every fix" },
  { name: "Nemotron 3 Super", job: "Maps the model, line by line and period by period" },
  { name: "Nemotron 3.5 Lightning", job: "Explains each error and answers your questions" },
];

export function Engine({ scene }: { scene: Scene }) {
  const frame = useCurrentFrame();
  const [l1, l2, l3, l4] = scene.lines;
  const split = clamp(frame, l3.start - 8, l3.start + 10);
  return (
    <AbsoluteFill style={{ background: C.night, fontFamily: FONT, color: "#fff" }}>
      <Wave strength={0.35} tint="74, 222, 128" />
      <AbsoluteFill style={{ opacity: 1 - split, filter: `blur(${split * 14}px)` }}>
        <div style={{ position: "absolute", top: 110, width: "100%", textAlign: "center", fontSize: 40, fontWeight: 600, color: "rgba(255,255,255,0.7)" }}>
          <Words text="Inside, two minds work together." at={l1.start} every={4} />
        </div>
        <div style={{ position: "absolute", left: 120, top: 250 }}>
          <Rise at={l2.start} distance={40}>
            <div style={{ fontSize: 26, fontWeight: 600, letterSpacing: "0.16em", textTransform: "uppercase", color: C.bright }}>NVIDIA Nemotron</div>
            <div style={{ fontSize: 96, fontWeight: 800, letterSpacing: "-0.045em", marginTop: 8 }}>reasons.</div>
          </Rise>
          <div style={{ marginTop: -40, marginLeft: -60 }}>
            <Network frame={frame} at={l2.start + 6} />
          </div>
        </div>
        <div style={{ position: "absolute", left: 1040, top: 250 }}>
          <Rise at={l2.start + Math.round(l2.frames * 0.5)} distance={40}>
            <div style={{ fontSize: 26, fontWeight: 600, letterSpacing: "0.16em", textTransform: "uppercase", color: C.bright }}>Calculation engine</div>
            <div style={{ fontSize: 96, fontWeight: 800, letterSpacing: "-0.045em", marginTop: 8 }}>calculates.</div>
          </Rise>
          <div style={{ marginTop: 50, opacity: clamp(frame, l2.start + Math.round(l2.frames * 0.5), l2.start + Math.round(l2.frames * 0.5) + 10) }}>
            <Calc frame={frame} at={l2.start + Math.round(l2.frames * 0.5) + 6} />
          </div>
        </div>
        <div style={{ position: "absolute", left: 960, top: 300, width: 1, height: 560, background: "rgba(255,255,255,0.15)", transform: `scaleY(${clamp(frame, l2.start, l2.start + 30)})`, transformOrigin: "top" }} />
      </AbsoluteFill>
      {frame >= l3.start - 8 && (
        <AbsoluteFill style={{ justifyContent: "center", padding: "0 140px", opacity: split }}>
          {MODELS.map((model, index) => {
            const at = l3.start + index * Math.round(l3.frames / 3.3);
            const on = clamp(frame, at, at + 14);
            return (
              <div key={model.name} style={{ display: "flex", alignItems: "center", gap: 60, padding: "34px 0", borderBottom: "1px solid rgba(255,255,255,0.14)", opacity: 0.25 + 0.75 * on, transform: `translateX(${(1 - on) * 40}px)` }}>
                <div style={{ width: 760, flexShrink: 0, whiteSpace: "nowrap", fontSize: 60, fontWeight: 800, letterSpacing: "-0.04em", color: on > 0.5 ? C.bright : "#fff" }}>{model.name}</div>
                <div style={{ fontSize: 34, lineHeight: 1.3, color: "rgba(255,255,255,0.8)" }}>{model.job}</div>
              </div>
            );
          })}
          <div style={{ marginTop: 70, display: "flex", alignItems: "baseline", gap: 24 }}>
            <Rise at={l4.start} distance={30}>
              <span style={{ fontSize: 30, color: "rgba(255,255,255,0.6)" }}>Running on</span>
            </Rise>
            <Rise at={l4.start + 8} distance={30}>
              <span style={{ fontSize: 64, fontWeight: 800, letterSpacing: "-0.04em" }}>Nebius Token Factory</span>
            </Rise>
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
}

function Count({ at, to, render, frame }: { at: number; to: number; render: (n: number) => string; frame: number }) {
  const p = clamp(frame, at, at + 26);
  return <>{render(to * p)}</>;
}

export function Proof({ scene }: { scene: Scene }) {
  const frame = useCurrentFrame();
  const L = scene.lines;
  const stats = [
    { at: L[0].start, big: (f: number) => <Count frame={f} at={L[0].start} to={98} render={(n) => `${Math.round(n)}%`} />, label: "of planted errors fixed correctly", sub: "86% with rules alone" },
    { at: L[1].start, big: () => <>0</>, label: "false alarms on values set on purpose", sub: "rules alone: 12 of 12" },
    { at: L[2].start, big: (f: number) => <Count frame={f} at={L[2].start} to={18} render={(n) => `${Math.round(n)}/20`} />, label: "on workbooks it had never seen", sub: "five Damodaran valuation workbooks" },
    { at: L[3].start, big: (f: number) => <Count frame={f} at={L[3].start} to={1.4} render={(n) => `${n.toFixed(1)}¢`} />, label: "per check, about a minute", sub: "median, on Nebius Token Factory" },
  ];
  return (
    <AbsoluteFill style={{ background: "#fff", fontFamily: FONT, color: C.ink }}>
      <Wave strength={0.6} />
      <AbsoluteFill style={{ flexDirection: "row", alignItems: "center", padding: "0 70px" }}>
        {stats.map((stat, index) => {
          const on = clamp(frame, stat.at - 4, stat.at + 14);
          return (
            <div key={index} style={{ flex: 1, padding: "0 34px", borderLeft: index ? `1px solid ${C.line}` : undefined, height: 420, display: "flex", flexDirection: "column", justifyContent: "flex-start", paddingTop: 40, boxSizing: "border-box", opacity: 0.15 + 0.85 * on, transform: `translateY(${(1 - on) * 50}px)` }}>
              <div style={{ fontSize: 124, fontWeight: 800, letterSpacing: "-0.06em", lineHeight: 1, color: on > 0.5 ? C.g3 : C.ink, fontVariantNumeric: "tabular-nums" }}>{stat.big(frame)}</div>
              <div style={{ marginTop: 26, fontSize: 34, fontWeight: 600, lineHeight: 1.2, letterSpacing: "-0.01em" }}>{stat.label}</div>
              <div style={{ marginTop: 14, fontSize: 24, color: C.muted }}>{stat.sub}</div>
            </div>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
}

export function Close({ scene }: { scene: Scene }) {
  const frame = useCurrentFrame();
  const [l1, l2] = scene.lines;
  const second = l1.start + Math.round(l1.frames * 0.5);
  const lift = clamp(frame, l2.start - 6, l2.start + 16);
  return (
    <AbsoluteFill style={{ background: "#fff", fontFamily: FONT, color: C.ink }}>
      <Wave strength={1} speed={0.016} />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", transform: `translateY(${-lift * 110}px)` }}>
        <div style={{ fontSize: 132, fontWeight: 800, letterSpacing: "-0.055em", lineHeight: 1.04, textAlign: "center" }}>
          <Words text="Every formula, checked." at={l1.start} every={4} />
          <br />
          <Words text="Every fix, proven." at={second} every={4} color={() => C.g3} />
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 250 }}>
        <Rise at={l2.start} distance={40}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 22 }}>
            <Brand size={86} />
            <div style={{ fontFamily: MONO, fontSize: 30, color: C.muted }}>model-x-ray.vercel.app</div>
          </div>
        </Rise>
      </AbsoluteFill>
      <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 150 }}>
        <Fade from={l2.start + 20} to={100000}>
          <Rise at={l2.start + 20} distance={20}>
            <div style={{ fontSize: 24, color: C.faint, letterSpacing: "0.04em" }}>Built with NVIDIA Nemotron for the Nebius × NVIDIA Global AI Hackathon. Runs on Nebius Token Factory.</div>
          </Rise>
        </Fade>
      </AbsoluteFill>
    </AbsoluteFill>
  );
}
