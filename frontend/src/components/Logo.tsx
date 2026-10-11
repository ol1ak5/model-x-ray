export default function Logo({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <path d="M6 5h9l19 30h-9z" fill="#0b5e36" />
      <path d="M34 5h-9L6 35h9z" fill="#1fa463" />
      <path d="M20.5 14.2 25 5h9l-9 14.2z" fill="#16884f" />
    </svg>
  );
}
