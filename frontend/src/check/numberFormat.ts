const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function sections(format: string): string[] {
  const parts: string[] = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < format.length; index++) {
    const char = format[index];
    if (char === "\\" && index + 1 < format.length) {
      current += char + format[++index];
      continue;
    }
    if (char === '"') quoted = !quoted;
    if (char === ";" && !quoted) {
      parts.push(current);
      current = "";
      continue;
    }
    current += char;
  }
  parts.push(current);
  return parts;
}

function literal(section: string): { text: string; marks: string } {
  let text = "";
  let marks = "";
  for (let index = 0; index < section.length; index++) {
    const char = section[index];
    if (char === "\\") {
      text += section[++index] ?? "";
      marks += " ";
    } else if (char === '"') {
      const end = section.indexOf('"', index + 1);
      const quoted = section.slice(index + 1, end < 0 ? undefined : end);
      text += quoted;
      marks += " ".repeat(quoted.length);
      index = end < 0 ? section.length : end;
    } else if (char === "[") {
      const end = section.indexOf("]", index);
      const tag = section.slice(index + 1, end < 0 ? undefined : end);
      const currency = tag.match(/^\$([^-]*)/);
      if (currency && currency[1]) {
        text += currency[1];
        marks += " ".repeat(currency[1].length);
      }
      index = end < 0 ? section.length : end;
    } else if (char === "_") {
      index++;
      text += " ";
      marks += " ";
    } else if (char === "*") {
      index++;
    } else {
      text += char;
      marks += char;
    }
  }
  return { text, marks };
}

function grouped(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function asDate(serial: number, pattern: string): string {
  const date = new Date(Date.UTC(1899, 11, 30) + Math.round(serial * 86400000));
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth();
  const day = date.getUTCDate();
  return pattern.replace(/yyyy|yy|mmmm|mmm|mm|m|dd|d/gi, (token) => {
    const lower = token.toLowerCase();
    if (lower === "yyyy") return String(year);
    if (lower === "yy") return String(year).slice(2);
    if (lower === "mmmm" || lower === "mmm") return MONTHS[month];
    if (lower === "mm") return String(month + 1).padStart(2, "0");
    if (lower === "m") return String(month + 1);
    if (lower === "dd") return String(day).padStart(2, "0");
    return String(day);
  });
}

export function formatNumber(value: number, format: string | undefined): string | null {
  if (!format || format === "General" || format === "@") return null;
  const parts = sections(format);
  const chosen = value < 0 && parts.length > 1 ? parts[1] : value === 0 && parts.length > 2 ? parts[2] : parts[0];
  const signed = value < 0 && parts.length === 1;
  const { text, marks } = literal(chosen);
  if (/[yd]|m{3,}/i.test(marks) && !/[0#?]/.test(marks)) return asDate(value, text);
  const first = marks.search(/[0#?]/);
  if (first < 0) return text;
  let last = first;
  for (let index = first; index < marks.length; index++) if (/[0#?.,]/.test(marks[index])) last = index;
  const pattern = marks.slice(first, last + 1);
  const percent = marks.includes("%");
  const [whole, fraction = ""] = pattern.split(".");
  const decimals = fraction.replace(/[^0#?]/g, "");
  const required = (decimals.match(/0/g) ?? []).length;
  let number = Math.abs(value) * (percent ? 100 : 1);
  const scaled = whole.match(/,+$/);
  if (scaled) number /= 1000 ** scaled[0].length;
  let [integer, rest = ""] = number.toFixed(decimals.length).split(".");
  rest = rest.replace(/0+$/, "");
  if (rest.length < required) rest = rest.padEnd(required, "0");
  const minimum = (whole.match(/0/g) ?? []).length;
  if (integer === "0" && minimum === 0) integer = "";
  integer = integer.padStart(minimum, "0");
  if (/,/.test(whole.replace(/,+$/, ""))) integer = grouped(integer);
  const shown = rest ? `${integer}.${rest}` : integer;
  return `${signed ? "-" : ""}${text.slice(0, first)}${shown}${text.slice(last + 1)}`;
}
