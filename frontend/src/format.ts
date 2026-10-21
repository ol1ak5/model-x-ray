import type { ModelMap } from "./api";

export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  if (value !== 0 && Math.abs(value) < 1) return `${(value * 100).toFixed(1)}%`;
  const text = Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return value < 0 ? `(${text})` : text;
}

export function ratio(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return `${(value * 100).toFixed(1)}%`;
}

export function figure(value: number | null | undefined, kind: string | null | undefined): string {
  return kind === "ratio" ? ratio(value) : money(value);
}

export function kindOf(map: ModelMap | null | undefined, label: string | null | undefined): string | null {
  if (!map || !label) return null;
  return map.rows.find((row) => row.label === label)?.kind ?? null;
}
