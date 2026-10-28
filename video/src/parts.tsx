import { createContext } from "react";
import type { CSSProperties, ReactNode } from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, HEIGHT, MONO, WIDTH } from "./theme";

export type Camera = "path" | "spotlight";

export const CameraStyle = createContext<Camera>("path");

export const ease = Easing.bezier(0.22, 1, 0.36, 1);

export function clamp(frame: number, from: number, to: number, a = 0, b = 1, easing = ease): number {
  return interpolate(frame, [from, to], [a, b], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing });
}

export function useSpring(at: number, damping = 18, stiffness = 140): number {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - at, fps, config: { damping, stiffness, mass: 0.9 } });
}

export function Wave({ strength = 1, tint = "40, 170, 100", speed = 0.012, lines = 70 }: { strength?: number; tint?: string; speed?: number; lines?: number }) {
  const frame = useCurrentFrame();
  const time = frame * speed;
  const paths: ReactNode[] = [];
  for (let line = 0; line < lines; line++) {
    const k = line / (lines - 1);
    let d = "";
    for (let x = -40; x <= WIDTH + 40; x += 24) {
      const u = x / WIDTH;
      const phase = k * 0.8;
      const y = HEIGHT * (0.95 - 0.75 * u) + Math.sin(u * 6 + time + phase) * HEIGHT * 0.22 + Math.sin(u * 2.3 - time * 0.6 + phase * 0.5) * HEIGHT * 0.07 + (k - 0.5) * HEIGHT * 0.2;
      d += `${x === -40 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }
    paths.push(<path key={line} d={d} fill="none" stroke={`rgba(${tint}, ${(0.1 + 0.12 * Math.sin(k * Math.PI)) * strength})`} strokeWidth={1.1} />);
  }
  return (
    <AbsoluteFill>
      <svg width={WIDTH} height={HEIGHT}>{paths}</svg>
    </AbsoluteFill>
  );
}

export function Rise({ at, children, distance = 60, style, blur = true, duration = 22 }: { at: number; children: ReactNode; distance?: number; style?: CSSProperties; blur?: boolean; duration?: number }) {
  const frame = useCurrentFrame();
  const p = clamp(frame, at, at + duration);
  return (
    <div style={{ opacity: p, transform: `translateY(${(1 - p) * distance}px)`, filter: blur ? `blur(${(1 - p) * 12}px)` : undefined, ...style }}>{children}</div>
  );
}

export function Fade({ from, to, children, style }: { from: number; to: number; children: ReactNode; style?: CSSProperties }) {
  const frame = useCurrentFrame();
  const p = clamp(frame, to, to + 12, 1, 0);
  return <div style={{ opacity: p, filter: `blur(${(1 - p) * 10}px)`, ...style }}>{frame >= from ? children : null}</div>;
}

export function Words({ text, at, every = 4, style, color }: { text: string; at: number; every?: number; style?: CSSProperties; color?: (word: string, index: number) => string | undefined }) {
  const frame = useCurrentFrame();
  return (
    <span style={style}>
      {text.split(" ").map((word, index) => {
        const p = clamp(frame, at + index * every, at + index * every + 16);
        return (
          <span key={index} style={{ display: "inline-block", opacity: p, transform: `translateY(${(1 - p) * 40}px)`, filter: `blur(${(1 - p) * 8}px)`, marginRight: "0.25em", color: color?.(word, index) }}>
            {word}
          </span>
        );
      })}
    </span>
  );
}

export function Roll({ value, at, size, color = "#fff", stagger = 2 }: { value: string; at: number; size: number; color?: string; stagger?: number }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  let digit = 0;
  return (
    <div style={{ display: "flex", fontFamily: FONT, fontWeight: 800, fontSize: size, lineHeight: 1, color, letterSpacing: "-0.04em", fontVariantNumeric: "tabular-nums" }}>
      {value.split("").map((char, index) => {
        if (!/\d/.test(char)) {
          const p = clamp(frame, at, at + 10);
          return (
            <span key={index} style={{ opacity: p }}>
              {char}
            </span>
          );
        }
        const target = Number(char);
        const order = digit++;
        const p = spring({ frame: frame - at - order * stagger, fps, config: { damping: 20, stiffness: 70, mass: 1 } });
        const turns = 10 + target;
        const position = p * turns;
        return (
          <span key={index} style={{ display: "inline-block", height: size, overflow: "hidden", position: "relative", width: "0.62em" }}>
            <span style={{ display: "block", transform: `translateY(${-(position % 10) * size}px)` }}>
              {Array.from({ length: 11 }, (_, n) => (
                <span key={n} style={{ display: "block", height: size, textAlign: "center" }}>
                  {n % 10}
                </span>
              ))}
            </span>
          </span>
        );
      })}
    </div>
  );
}

export function Logo({ size, draw = 1 }: { size: number; draw?: number }) {
  const len = 260;
  return (
    <svg width={size} height={size} viewBox="0 0 64 64">
      <defs>
        <linearGradient id="lg" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor={C.g1} />
          <stop offset=".55" stopColor={C.g2} />
          <stop offset="1" stopColor={C.g3} />
        </linearGradient>
      </defs>
      <path d="M12 4h28l14 14v38a4 4 0 0 1-4 4H12a4 4 0 0 1-4-4V8a4 4 0 0 1 4-4z" fill="url(#lg)" fillOpacity={Math.min(1, draw * 1.4)} stroke={C.bright} strokeWidth={1.2} strokeDasharray={len} strokeDashoffset={len * (1 - draw)} />
      <path d="M40 4v10a4 4 0 0 0 4 4h10" fill={C.bright} fillOpacity={0.55 * draw} />
      <g stroke="#fff" strokeOpacity={0.3 * draw} strokeWidth="1.5">
        <path d="M15 30h34M15 40h34M15 50h34M27 24v30" />
      </g>
      <rect x="30" y="33" width="16" height="14" rx="2.5" fill="#fff" opacity={Math.max(0, draw * 2 - 1)} />
      <path d="M34 40l2.6 2.6 5-5.4" fill="none" stroke={C.g3} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={14} strokeDashoffset={14 * (1 - Math.max(0, draw * 2 - 1))} />
    </svg>
  );
}

export function Brand({ size = 64, color = C.ink }: { size?: number; color?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: size * 0.3, fontFamily: FONT, fontWeight: 700, fontSize: size * 0.62, color, letterSpacing: "-0.02em" }}>
      <Logo size={size} />
      <span>
        Model <span style={{ color: C.g3 }}>X-Ray</span>
      </span>
    </div>
  );
}

export const mono: CSSProperties = { fontFamily: MONO };

export const label: CSSProperties = { fontFamily: FONT, fontWeight: 600, fontSize: 22, letterSpacing: "0.16em", textTransform: "uppercase", color: C.g3 };
