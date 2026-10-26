import { useId } from "react";

export function Logo() {
  const id = useId();
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#0a4a29" />
          <stop offset=".55" stopColor="#0d5c33" />
          <stop offset="1" stopColor="#12814a" />
        </linearGradient>
      </defs>
      <path d="M12 4h28l14 14v38a4 4 0 0 1-4 4H12a4 4 0 0 1-4-4V8a4 4 0 0 1 4-4z" fill={`url(#${id})`} />
      <path d="M40 4v10a4 4 0 0 0 4 4h10" fill="#4ade80" fillOpacity=".55" />
      <g stroke="#fff" strokeOpacity=".3" strokeWidth="1.5">
        <path d="M15 30h34M15 40h34M15 50h34M27 24v30" />
      </g>
      <rect x="30" y="33" width="16" height="14" rx="2.5" fill="#fff" />
      <path d="M34 40l2.6 2.6 5-5.4" fill="none" stroke="#12814a" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Brand({ onHome }: { onHome: () => void }) {
  return (
    <button type="button" className="brand" onClick={onHome}>
      <Logo />
      <span>
        Model <span className="xr">X-Ray</span>
      </span>
    </button>
  );
}
