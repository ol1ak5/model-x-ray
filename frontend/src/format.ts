export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  if (value !== 0 && Math.abs(value) < 1) return `${(value * 100).toFixed(1)}%`;
  const text = Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return value < 0 ? `(${text})` : text;
}
