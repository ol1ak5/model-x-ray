import { useState } from "react";

import type { SheetWindow } from "../api";
import { money } from "../format";

export type Marks = { suspicious: Set<string>; confirmed: Set<string>; target: string | null; after: Record<string, number>; patch: { cell: string; old_formula: string; new_formula: string } | null };

const MENU = ["File", "Home", "Insert", "Formulas", "Data", "Review", "View"];

export default function SheetGrid({ sheet, marks, title, showFormulaBar = true }: { sheet: SheetWindow; marks: Marks; title: string; showFormulaBar?: boolean }) {
  const firstMarked = marks.patch?.cell ?? [...marks.confirmed][0] ?? [...marks.suspicious][0] ?? marks.target;
  const [selected, setSelected] = useState<string | null>(firstMarked);
  const cell = sheet.rows.flatMap((row) => row.cells).find((item) => item.ref === selected);
  const fixed = marks.patch && selected === marks.patch.cell;

  return (
    <section className="sheet card-flat" aria-label={title}>
      <div className="sheet-menu" aria-hidden="true">
        {MENU.map((item) => (
          <span key={item}>{item}</span>
        ))}
        <span className="sheet-tab">{sheet.sheet}</span>
      </div>
      {showFormulaBar && (
      <div className="formula-bar">
        <span className="fx">fx</span>
        <span className="mono ref">{selected ?? ""}</span>
        {fixed && marks.patch ? (
          <>
            <span className="mono old">{marks.patch.old_formula}</span>
            <span className="mono new">{marks.patch.new_formula}</span>
          </>
        ) : (
          <span className="mono">{cell ? (cell.formula ?? money(cell.value)) : ""}</span>
        )}
      </div>
      )}
      <div className="grid-scroll">
        <table className="grid">
          <thead>
            <tr>
              <th className="corner" />
              <th className="label-col">&nbsp;</th>
              {sheet.columns.map((column) => (
                <th key={column.letter} scope="col">
                  <span className="letter">{column.letter}</span>
                  <span className="period">{column.header}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.rows.map((row) => (
              <tr key={row.row} className={/^ebitda$/i.test(row.label.trim()) ? "total-row" : ""}>
                <th scope="row" className="row-number">
                  {row.row}
                </th>
                <td className="label-col">{row.label}</td>
                {row.cells.map((item) => {
                  const state = marks.confirmed.has(item.ref) ? "confirmed" : marks.suspicious.has(item.ref) ? "suspicious" : marks.target === item.ref ? "target" : "";
                  const after = marks.after[item.ref];
                  const changed = after !== undefined && item.value !== null && Math.abs(after - item.value) > 1e-9;
                  return (
                    <td key={item.ref} className={`num ${state} ${showFormulaBar && selected === item.ref ? "selected" : ""}`}>
                      <button type="button" aria-label={`${item.ref}${state ? `, ${state}` : ""}`} onClick={() => setSelected(item.ref)}>
                        {money(item.value)}
                        {changed && <span className="after">{money(after)}</span>}
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
