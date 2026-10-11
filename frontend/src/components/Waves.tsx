const LINES = 22;

function wave(index: number): string {
  const points: string[] = [];
  for (let x = 0; x <= 1600; x += 40) {
    const phase = index * 0.35;
    const y = 120 + index * 7 + Math.sin(x / 210 + phase) * (26 + index * 1.6) + Math.sin(x / 90 + phase * 2) * 6;
    points.push(`${x},${y.toFixed(1)}`);
  }
  return points.join(" ");
}

export default function Waves() {
  return (
    <svg className="waves" viewBox="0 0 1600 320" preserveAspectRatio="none" aria-hidden="true">
      {Array.from({ length: LINES }, (_, index) => (
        <polyline key={index} points={wave(index)} fill="none" strokeWidth="1" style={{ opacity: 0.12 + (index / LINES) * 0.5 }} />
      ))}
      {Array.from({ length: 33 }, (_, index) => (
        <line key={`v${index}`} x1={index * 50} y1="90" x2={index * 50 - 60} y2="320" strokeWidth="0.6" style={{ opacity: 0.12 }} />
      ))}
    </svg>
  );
}
