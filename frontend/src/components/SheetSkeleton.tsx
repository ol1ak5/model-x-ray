import type { CSSProperties } from "react";

import grid from "./SheetGrid.module.css";
import stage from "./Stage.module.css";
import styles from "./SheetSkeleton.module.css";

const MENU = ["File", "Home", "Insert", "Formulas", "Data", "Review", "View"];
const LETTERS = ["F", "G", "H", "I", "J"];
const ROWS = [3, 4, 5, 6, 7, 8, 9, 10];

function width(seed: number): CSSProperties {
  return { "--w": `${44 + (seed % 4) * 13}%` } as CSSProperties;
}

export default function SheetSkeleton({ note }: { note: string }) {
  return (
    <div className={stage.stage}>
      <div className={stage.board}>
        <section className={`${grid.sheet} ${grid.light}`} aria-label="Sheet" aria-busy="true">
          <div className={grid.menu} aria-hidden="true">
            {MENU.map((item) => (
              <span key={item}>{item}</span>
            ))}
            <span className={grid.tab}>
              <span className={styles.bar} />
            </span>
          </div>
          <div className={grid.formulaBar}>
            <span className={grid.fx}>fx</span>
            <span className={styles.bar} />
            <span className={styles.note}>{note}</span>
          </div>
          <div className={grid.scroll}>
            <table className={grid.grid}>
              <colgroup>
                <col className={grid.colRow} />
                <col className={grid.colLabel} />
                {LETTERS.map((letter) => (
                  <col key={letter} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  <th className={grid.corner} />
                  <th className={grid.labelHead}>&nbsp;</th>
                  {LETTERS.map((letter) => (
                    <th key={letter} scope="col">
                      {letter}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className={grid.periodRow}>
                  <th scope="row" className={grid.rowNumber}>
                    2
                  </th>
                  <td className={grid.labelCol} />
                  {LETTERS.map((letter) => (
                    <td key={letter} className={grid.period}>
                      <span className={styles.bar} style={width(0)} />
                    </td>
                  ))}
                </tr>
                {ROWS.map((row, index) => (
                  <tr key={row}>
                    <th scope="row" className={grid.rowNumber}>
                      {row}
                    </th>
                    <td className={grid.labelCol}>
                      <span className={`${styles.bar} ${styles.left}`} style={width(index + 1)} />
                    </td>
                    {LETTERS.map((letter, column) => (
                      <td key={letter} className={grid.num}>
                        <span className={styles.bar} style={width(index + column + 2)} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
