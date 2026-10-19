import { useState } from "react";

import type { SheetWindow } from "../api";
import { money } from "../format";
import styles from "./SheetGrid.module.css";

export type Marks = { suspicious: Set<string>; confirmed: Set<string>; traced: Set<string>; target: string | null; after: Record<string, number>; patch: { cell: string; old_formula: string; new_formula: string } | null };

const MENU = ["File", "Home", "Insert", "Formulas", "Data", "Review", "View"];

export default function SheetGrid({ sheet, marks, title, showFormulaBar = true, light = false }: { sheet: SheetWindow; marks: Marks; title: string; showFormulaBar?: boolean; light?: boolean }) {
  const firstMarked = marks.patch?.cell ?? [...marks.confirmed][0] ?? [...marks.suspicious][0] ?? marks.target;
  const [selected, setSelected] = useState<string | null>(firstMarked);
  const cell = sheet.rows.flatMap((row) => row.cells).find((item) => item.ref === selected);
  const fixed = marks.patch && selected === marks.patch.cell;

  return (
    <section className={`${styles.sheet} ${light ? styles.light : ""}`} aria-label={title}>
      <div className={styles.menu} aria-hidden="true">
        {MENU.map((item) => (
          <span key={item}>{item}</span>
        ))}
        <span className={styles.tab}>{sheet.sheet}</span>
      </div>
      {showFormulaBar && (
        <div className={styles.formulaBar}>
          <span className={styles.fx}>fx</span>
          <span className={`mono ${styles.ref}`}>{selected ?? ""}</span>
          {fixed && marks.patch ? (
            <>
              <span className={`mono ${styles.old}`}>{marks.patch.old_formula}</span>
              <span className={`mono ${styles.new}`}>{marks.patch.new_formula}</span>
            </>
          ) : (
            <span className={`mono ${styles.value}`} key={selected}>
              {cell ? (cell.formula ?? money(cell.value)) : ""}
            </span>
          )}
        </div>
      )}
      <div className={styles.scroll}>
        <table className={styles.grid} style={{ minWidth: `${(96 + sheet.columns.length * (Object.keys(marks.after).length > 0 ? 136 : 64)) / 16}rem` }}>
          <colgroup>
            <col className={styles.colRow} />
            <col className={styles.colLabel} />
            {sheet.columns.map((column) => (
              <col key={column.letter} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th className={styles.corner} />
              <th className={styles.labelHead}>&nbsp;</th>
              {sheet.columns.map((column) => (
                <th key={column.letter} scope="col" aria-label={column.header}>
                  {column.letter}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className={styles.periodRow}>
              <th scope="row" className={styles.rowNumber}>
                {sheet.header_row ?? ""}
              </th>
              <td className={styles.labelCol} />
              {sheet.columns.map((column) => (
                <td key={column.letter} className={styles.period}>
                  {column.header}
                </td>
              ))}
            </tr>
            {sheet.rows.map((row) => (
              <tr key={row.row} className={/^ebitda$/i.test(row.label.trim()) ? styles.totalRow : ""}>
                <th scope="row" className={styles.rowNumber}>
                  {row.row}
                </th>
                <td className={styles.labelCol}>{row.label}</td>
                {row.cells.map((item) => {
                  const state = marks.confirmed.has(item.ref) ? "confirmed" : marks.suspicious.has(item.ref) ? "suspicious" : marks.target === item.ref ? "target" : marks.traced.has(item.ref) ? "traced" : "";
                  const after = marks.after[item.ref];
                  const changed = after !== undefined && item.value !== null && Math.abs(after - item.value) > 1e-9;
                  return (
                    <td key={item.ref} data-ref={item.ref} data-row={row.row} className={`${styles.num} ${styles[state as keyof typeof styles] ?? ""} ${showFormulaBar && selected === item.ref ? styles.selected : ""}`}>
                      <button type="button" aria-label={`${item.ref}${state ? `, ${state}` : ""}`} onClick={() => setSelected(item.ref)}>
                        {money(item.value)}
                        {changed && <span className={styles.after}>→ {money(after)}</span>}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
