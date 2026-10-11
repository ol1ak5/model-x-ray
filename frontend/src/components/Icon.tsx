const PATHS: Record<string, string> = {
  scan: "M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2M8 12h8",
  trace: "M6 4v6a4 4 0 0 0 4 4h8M14 10l4 4-4 4",
  shield: "M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3zM9 12l2 2 4-4",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20a8 8 0 0 1 16 0",
  upload: "M12 16V4M7 9l5-5 5 5M5 20h14",
  play: "M8 5v14l11-7z",
  grid: "M4 4h16v16H4zM4 10h16M10 4v16",
  spark: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6",
  file: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
};

export default function Icon({ name, size = 20 }: { name: keyof typeof PATHS; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}
