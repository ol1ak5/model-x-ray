import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import type { WorkbookSheet, WorkbookView } from "../api";
import { splitRef } from "../findings";

export type Marks = { error: string; dependents: string[] } | null;

export function letters(column: number): string {
  let name = "";
  for (let rest = column; rest > 0; rest = Math.floor((rest - 1) / 26)) name = String.fromCharCode(65 + ((rest - 1) % 26)) + name;
  return name;
}

function position(address: string): [number, number] {
  const match = address.match(/^([A-Z]+)(\d+)$/);
  if (!match) return [1, 1];
  const column = [...match[1]].reduce((total, char) => total * 26 + char.charCodeAt(0) - 64, 0);
  return [column, Number(match[2])];
}

export function shown(value: WorkbookView["sheets"][number]["cells"][number]["value"]): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(10)));
  return value;
}

function Grid({ sheet, marks, selected, onSelect }: { sheet: WorkbookSheet; marks: Marks; selected: string; onSelect: (address: string) => void }) {
  const byRef = useMemo(() => new Map(sheet.cells.map((cell) => [cell.ref, cell])), [sheet]);
  const columns = Array.from({ length: Math.max(sheet.columns, 6) }, (_, index) => letters(index + 1));
  const rows = Array.from({ length: Math.max(sheet.rows, 12) }, (_, index) => index + 1);
  const [errorSheet, errorAddress] = marks ? splitRef(marks.error) : ["", ""];
  const dependents = new Set((marks?.dependents ?? []).filter((ref) => splitRef(ref)[0] === sheet.name).map((ref) => splitRef(ref)[1]));
  return (
    <table className="grid">
      <thead>
        <tr>
          <th />
          {columns.map((column) => (
            <th key={column}>{column}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row}>
            <td className="rn">{row}</td>
            {columns.map((column) => {
              const address = `${column}${row}`;
              const cell = byRef.get(address);
              const classes = [typeof cell?.value === "number" ? "num" : "", errorSheet === sheet.name && errorAddress === address ? "m-err" : dependents.has(address) ? "m-dep" : "", address === selected ? "sel" : ""].filter(Boolean).join(" ");
              return (
                <td key={address} data-ref={address} className={classes || undefined} onClick={() => onSelect(address)}>
                  {shown(cell?.value ?? null)}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function SheetDialog({ open, name, sheet: wanted, title, marks, load, onClose }: { open: boolean; name: string; sheet: string; title: string; marks: Marks; load: () => Promise<WorkbookView>; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [book, setBook] = useState<WorkbookView | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [current, setCurrent] = useState(wanted);
  const [selected, setSelected] = useState("A1");

  useEffect(() => {
    setCurrent(wanted);
    setSelected(marks && splitRef(marks.error)[0] === wanted ? splitRef(marks.error)[1] : "A1");
  }, [wanted, marks, open]);

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) {
      if (typeof element.showModal === "function") element.showModal();
      else element.setAttribute("open", "");
    }
    if (!open && element.open) {
      if (typeof element.close === "function") element.close();
      else element.removeAttribute("open");
    }
  }, [open]);

  useEffect(() => {
    if (!open || book) return;
    load()
      .then(setBook)
      .catch((reason: unknown) => setFailure(reason instanceof Error ? reason.message : "The sheets could not be loaded."));
  }, [open, book, load]);

  const sheet = book?.sheets.find((candidate) => candidate.name === current) ?? null;
  const cell = sheet?.cells.find((candidate) => candidate.ref === selected);

  function move(event: KeyboardEvent<HTMLDivElement>) {
    const steps: Record<string, [number, number]> = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] };
    const step = steps[event.key];
    if (!step) return;
    event.preventDefault();
    const [column, row] = position(selected);
    setSelected(`${letters(Math.max(1, column + step[0]))}${Math.max(1, row + step[1])}`);
  }

  return (
    <dialog ref={dialog} onClose={onClose} aria-label={title}>
      <div className="dhead">
        <span>{title}</span>
        <button type="button" aria-label="Close" onClick={onClose}>
          ×
        </button>
      </div>
      {marks && (
        <div className="mkey">
          {splitRef(marks.error)[0] === current && <span className="k1">The error</span>}
          <span className="k2">Cells that depend on it</span>
          <span className="k3">Marks are only shown here, your file is not changed</span>
        </div>
      )}
      <div className="xl" onKeyDown={move} tabIndex={-1}>
        <div className="titlebar">
          <i>X</i>
          {name}
          <small>Original file</small>
        </div>
        <div className="fx">
          <span className="nm">{selected}</span>
          <em>fx</em>
          <span>{cell?.formula ?? shown(cell?.value ?? null)}</span>
        </div>
        <div className="scroll">
          {sheet ? <Grid sheet={sheet} marks={marks} selected={selected} onSelect={setSelected} /> : <p className="loading">{failure ?? "Opening the workbook…"}</p>}
        </div>
        <div className="tabs" role="tablist">
          {(book?.sheets ?? []).map((candidate) => (
            <button type="button" role="tab" aria-selected={candidate.name === current} key={candidate.name} className={candidate.name === current ? "on" : undefined} onClick={() => setCurrent(candidate.name)}>
              {candidate.name}
            </button>
          ))}
        </div>
      </div>
    </dialog>
  );
}
