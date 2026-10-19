import styles from "./WireKey.module.css";

export default function WireKey() {
  return (
    <span className={styles.key}>
      <svg className={styles.glyph} viewBox="0 0 34 8" aria-hidden="true">
        <circle cx="3" cy="4" r="2.5" />
        <path className={styles.line} d="M 3 4 H 26" />
        <path className={styles.head} d="M 26 1 L 32 4 L 26 7 Z" />
      </svg>
      contributes
    </span>
  );
}
