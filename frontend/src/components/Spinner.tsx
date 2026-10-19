import styles from "./Spinner.module.css";

export default function Spinner({ size = 1.25 }: { size?: number }) {
  return <span className={styles.spinner} style={{ width: `${size}rem`, height: `${size}rem` }} aria-hidden="true" />;
}
