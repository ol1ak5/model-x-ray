const COLUMNS = 64;
const ROWS = 22;
const WIDTH = 1600;
const HEIGHT = 300;
const HILLS = [
  { u: 0.12, d: 0.55, h: 1.0, w: 0.09 },
  { u: 0.34, d: 0.35, h: 0.8, w: 0.1 },
  { u: 0.52, d: 0.7, h: 1.25, w: 0.12 },
  { u: 0.72, d: 0.45, h: 0.95, w: 0.09 },
  { u: 0.9, d: 0.65, h: 1.1, w: 0.1 },
];

function height(u: number, d: number): number {
  return HILLS.reduce((sum, hill) => sum + hill.h * Math.exp(-((u - hill.u) ** 2 + ((d - hill.d) * 0.8) ** 2) / (2 * hill.w ** 2)), 0) + 0.12 * Math.sin(u * 22 + d * 6);
}

function point(u: number, d: number): [number, number] {
  const spread = 0.55 + 0.75 * d;
  const x = WIDTH / 2 + (u - 0.5) * WIDTH * spread * 1.15;
  const y = 70 + d ** 1.25 * (HEIGHT - 90) - height(u, d) * (26 + 95 * d);
  return [x, y];
}

function line(points: [number, number][]): string {
  return points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
}

export default function Waves() {
  const rows = Array.from({ length: ROWS }, (_, r) => r / (ROWS - 1));
  const columns = Array.from({ length: COLUMNS }, (_, c) => c / (COLUMNS - 1));
  return (
    <svg className="waves" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="wave-fade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="white" stopOpacity="0" />
          <stop offset="0.3" stopColor="white" stopOpacity="0.35" />
          <stop offset="0.6" stopColor="white" stopOpacity="0.8" />
          <stop offset="1" stopColor="white" stopOpacity="1" />
        </linearGradient>
        <linearGradient id="wave-sides" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="white" stopOpacity="0" />
          <stop offset="0.12" stopColor="white" stopOpacity="1" />
          <stop offset="0.88" stopColor="white" stopOpacity="1" />
          <stop offset="1" stopColor="white" stopOpacity="0" />
        </linearGradient>
        <mask id="wave-mask">
          <rect width={WIDTH} height={HEIGHT} fill="url(#wave-fade)" />
          <rect width={WIDTH} height={HEIGHT} fill="url(#wave-sides)" style={{ mixBlendMode: "multiply" }} />
        </mask>
      </defs>
      <g mask="url(#wave-mask)" fill="none">
        {rows.map((d) => (
          <polyline key={`r${d}`} points={line(columns.map((u) => point(u, d)))} strokeWidth={0.6 + d * 0.9} style={{ opacity: 0.25 + d * 0.6 }} />
        ))}
        {columns.map((u) => (
          <polyline key={`c${u}`} points={line(rows.map((d) => point(u, d)))} strokeWidth="0.6" style={{ opacity: 0.35 }} />
        ))}
      </g>
      <line x1="0" y1={HEIGHT - 1} x2={WIDTH} y2={HEIGHT - 1} className="wave-horizon" />
    </svg>
  );
}
