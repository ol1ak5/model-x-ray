import type { ReactNode } from "react";

import styles from "./Chip.module.css";

export type ChipTone = "neutral" | "green" | "red" | "amber" | "blue";

export default function Chip({ tone = "neutral", pulse = false, className, children }: { tone?: ChipTone; pulse?: boolean; className?: string; children: ReactNode }) {
  const classes = [styles.chip, styles[tone], pulse ? styles.pulse : "", className].filter(Boolean).join(" ");
  return <span className={classes}>{children}</span>;
}
