import hashlib
import math
import re
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import TypedDict

CellContent = float | str | bool
Value = float | str | bool | None


class CellMetadata(TypedDict):
    note: str | None
    font_color: str | None
    number_format: str | None

TOKEN_PATTERN = re.compile(
    r"""
    (?P<ws>\s+)
    |(?P<string>"(?:[^"]|"")*")
    |(?P<error>(?:(?:'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_&.]*)!)?\#(?:REF!|N/A|DIV/0!|VALUE!|NAME\?|NUM!|NULL!))
    |(?P<span>(?:(?:'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_&.]*)!)?(?:\$?[0-9]+:\$?[0-9]+|\$?[A-Za-z]{1,3}:\$?[A-Za-z]{1,3})(?![A-Za-z0-9_]))
    |(?P<func>[A-Za-z_][A-Za-z0-9_.]*(?=\())
    |(?P<ref>(?:(?:'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_&.]*)!)?\$?[A-Za-z]{1,3}\$?[0-9]+(?::\$?[A-Za-z]{1,3}\$?[0-9]+)?(?![A-Za-z0-9_]))
    |(?P<number>[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?%?)
    |(?P<bool>(?:TRUE|FALSE)(?![A-Za-z0-9_.]))
    |(?P<name>[A-Za-z_\\][A-Za-z0-9_.]*)
    |(?P<op><=|>=|<>|[-+*/^&=<>])
    |(?P<lparen>\()
    |(?P<rparen>\))
    |(?P<comma>,)
    """,
    re.VERBOSE,
)

INFORMATION_FUNCTIONS = ("ISERROR", "ISNUMBER", "ISTEXT", "ISBLANK")
SPAN_PATTERN = re.compile(r"(\$?)([0-9]+|[A-Za-z]{1,3})")
MAX_ROWS = 1048576
MAX_COLUMNS = 16384
CELL_PATTERN = re.compile(r"(\$?)([A-Za-z]{1,3})(\$?)([0-9]+)")

SUPPORTED_FUNCTIONS = (
    "SUM", "AVERAGE", "MIN", "MAX", "IF", "ROUND", "ABS",
    "IFERROR", "AND", "OR", "NOT", "SUMIF", "SUMIFS", "COUNTIF", "COUNTIFS", "SUMPRODUCT", "INDEX", "MATCH", "VLOOKUP", "XLOOKUP", "EOMONTH",
    "YEAR", "MONTH", "DAY", "DATE", "EDATE", "NPV", "XNPV",
    "POWER", "ROUNDDOWN", "INT", "MOD", "PPMT", "XIRR",
    "PMT", "IRR", "HLOOKUP", "COUNT", "COUNTA", "ISERROR", "ISTEXT", "ISNUMBER", "ISBLANK", "LARGE", "SMALL", "CHOOSE",
    "EXP", "LN", "NORMSDIST", "NORM.S.DIST",
)
YEAR_RANGE = (1900, 2100)
PERIOD_INDEX_RANGE = (-50, 200)
SERIAL_RANGE = (1, 2958465)
PERIOD_PRIORITY = {"year": 0, "date": 1, "index": 2}
STACKED_HEADER_ROWS = 3
PERIOD_WORDS = re.compile(r"(?i)\b(base|current|terminal|actual|ltm|ntm|today|stable|steady|normali[sz]ed|year 0|beyond|after)\b")
DATE_FORMAT = re.compile(r"(?i)(yy|mmm|dd?[/.-]|[/.-]dd?|m/)")
FUNCTION_PREFIXES = ("_XLFN._XLWS.", "_XLFN.", "_XLWS.")
EXCEL_EPOCH = date(1899, 12, 30)
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
CRITERIA = re.compile(r"(<=|>=|<>|<|>|=)?(.*)", re.DOTALL)


class FormulaError(Exception):
    pass


class UnsupportedFormulaError(FormulaError):
    pass


class CircularReferenceError(FormulaError):
    pass


class Grid(list):
    def __init__(self, values: list["Value"], width: int) -> None:
        super().__init__(values)
        self.width = width

    @property
    def height(self) -> int:
        return len(self) // self.width if self.width else 0

    def at(self, row: int, column: int) -> "Value":
        return self[(row - 1) * self.width + (column - 1)]

    def column(self, column: int) -> list["Value"]:
        return [self.at(row, column) for row in range(1, self.height + 1)]

    def row(self, row: int) -> list["Value"]:
        return [self.at(row, column) for column in range(1, self.width + 1)]


@dataclass
class Failure:
    error: "FormulaError"


@dataclass(frozen=True)
class Token:
    kind: str
    text: str


@dataclass(frozen=True)
class CellAddress:
    column: int
    row: int
    absolute_column: bool = False
    absolute_row: bool = False


@dataclass(frozen=True)
class Reference:
    sheet: str | None
    sheet_text: str
    start: CellAddress
    end: CellAddress | None


def column_number(letters: str) -> int:
    number = 0
    for letter in letters.upper():
        number = number * 26 + ord(letter) - ord("A") + 1
    return number


def column_letters(number: int) -> str:
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def split_ref(ref: str) -> tuple[str, CellAddress]:
    sheet, cell = ref.rsplit("!", 1)
    match = CELL_PATTERN.fullmatch(cell)
    if match is None:
        raise FormulaError(f"Invalid cell reference: {ref}")
    return sheet, CellAddress(column_number(match.group(2)), int(match.group(4)))


def make_ref(sheet: str, address: CellAddress) -> str:
    return f"{sheet}!{column_letters(address.column)}{address.row}"


def normalize_ref(ref: str) -> str:
    sheet, address = split_ref(ref.replace("$", ""))
    return make_ref(sheet, address)


def expand_range(text: str) -> list[str]:
    sheet_text, _, cells = text.rpartition("!")
    if not sheet_text:
        raise FormulaError(f"Range must include a sheet: {text}")
    sheet = sheet_text[1:-1].replace("''", "'") if sheet_text.startswith("'") else sheet_text
    parts = cells.split(":")
    if len(parts) > 2:
        raise FormulaError(f"Invalid range: {text}")
    _, start = split_ref(f"{sheet}!{parts[0]}")
    _, end = split_ref(f"{sheet}!{parts[-1]}")
    return [
        make_ref(sheet, CellAddress(column, row))
        for row in range(min(start.row, end.row), max(start.row, end.row) + 1)
        for column in range(min(start.column, end.column), max(start.column, end.column) + 1)
    ]


EXTERNAL_LINK = re.compile(r"\[[0-9]+\][^!\"]*!")


def tokenize(formula: str) -> list[Token]:
    if EXTERNAL_LINK.search(formula):
        raise UnsupportedFormulaError(f"Formula {formula!r} reads another workbook; links to other files are not supported, so open the linked file and paste its values")
    tokens: list[Token] = []
    position = 1 if formula.startswith("=") else 0
    while position < len(formula):
        match = TOKEN_PATTERN.match(formula, position)
        if match is None:
            raise UnsupportedFormulaError(f"Cannot read formula {formula!r} at position {position}")
        kind = match.lastgroup or ""
        if kind != "ws":
            tokens.append(Token(kind, match.group()))
        position = match.end()
    return tokens


def parse_reference(text: str) -> Reference:
    sheet_text, _, cells = text.rpartition("!")
    sheet = sheet_text[1:-1].replace("''", "'") if sheet_text.startswith("'") else sheet_text or None
    parts = []
    for part in cells.split(":"):
        match = CELL_PATTERN.fullmatch(part)
        if match is None:
            raise FormulaError(f"Invalid reference: {text}")
        parts.append(CellAddress(column_number(match.group(2)), int(match.group(4)), match.group(1) == "$", match.group(3) == "$"))
    return Reference(sheet, sheet_text, parts[0], parts[1] if len(parts) > 1 else None)


def expand(reference: Reference, base_sheet: str) -> list[str]:
    sheet = reference.sheet or base_sheet
    end = reference.end or reference.start
    return [
        make_ref(sheet, CellAddress(column, row))
        for row in range(min(reference.start.row, end.row), max(reference.start.row, end.row) + 1)
        for column in range(min(reference.start.column, end.column), max(reference.start.column, end.column) + 1)
    ]


@dataclass(frozen=True)
class Span:
    sheet: str | None
    sheet_text: str
    rows: bool
    first: int
    last: int
    absolute_first: bool
    absolute_last: bool


def parse_span(text: str) -> Span:
    sheet_text, _, cells = text.rpartition("!")
    sheet = sheet_text[1:-1].replace("''", "'") if sheet_text.startswith("'") else sheet_text or None
    (first_dollar, first), (last_dollar, last) = (SPAN_PATTERN.fullmatch(part).groups() for part in cells.split(":"))
    rows = first.isdigit()
    first_number, last_number = (int(part) if rows else column_number(part) for part in (first, last))
    return Span(sheet, sheet_text, rows, first_number, last_number, first_dollar == "$", last_dollar == "$")


def span_text(span: Span, first: int, last: int) -> str:
    prefix = f"{span.sheet_text}!" if span.sheet_text else ""
    show = (lambda n: str(n)) if span.rows else column_letters
    return f"{prefix}{'$' if span.absolute_first else ''}{show(first)}:{'$' if span.absolute_last else ''}{show(last)}"


def relative_part(address: CellAddress, base: CellAddress) -> str:
    if address.absolute_row:
        row = f"R{address.row}"
    else:
        offset = address.row - base.row
        row = "R" if offset == 0 else f"R[{offset}]"
    if address.absolute_column:
        column = f"C{address.column}"
    else:
        offset = address.column - base.column
        column = "C" if offset == 0 else f"C[{offset}]"
    return row + column


def shifted_part(address: CellAddress, delta_row: int, delta_column: int) -> str:
    row = address.row if address.absolute_row else address.row + delta_row
    column = address.column if address.absolute_column else address.column + delta_column
    column_text = f"${column_letters(column)}" if address.absolute_column else column_letters(column)
    row_text = f"${row}" if address.absolute_row else str(row)
    return column_text + row_text


def to_serial(value: Value) -> float:
    if isinstance(value, str) and ISO_DATE.match(value):
        return float((datetime.fromisoformat(value).date() - EXCEL_EPOCH).days)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise FormulaError(f"{value!r} is not a date")


def from_serial(serial: float) -> date:
    return EXCEL_EPOCH + timedelta(days=int(serial))


def end_of_month(start: date, months: int) -> date:
    month_index = start.year * 12 + start.month - 1 + months
    year, month = divmod(month_index, 12)
    first_of_next = date(year + (month + 1) // 12, (month + 1) % 12 + 1, 1)
    return first_of_next - timedelta(days=1)


def shift_months(start: date, months: int) -> date:
    year, month = divmod(start.year * 12 + start.month - 1 + months, 12)
    first = date(year, month + 1, 1)
    return first.replace(day=min(start.day, end_of_month(first, 0).day))


def is_label_text(content: object) -> bool:
    return isinstance(content, str) and not content.startswith("=") and content.strip() != "" and not ISO_DATE.match(content)


def is_number(value: Value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def as_date_serial(left: Value, right: Value) -> tuple[Value, Value]:
    if isinstance(left, str) and ISO_DATE.match(left) and is_number(right):
        return to_serial(left), right
    if isinstance(right, str) and ISO_DATE.match(right) and is_number(left):
        return left, to_serial(right)
    return left, right


def same_value(left: Value, right: Value) -> bool:
    left, right = as_date_serial(left, right)
    if isinstance(left, str) and isinstance(right, str):
        return left.lower() == right.lower()
    if is_number(left) and is_number(right):
        return float(left) == float(right)
    return left == right


def not_greater(item: Value, target: Value) -> bool:
    item, target = as_date_serial(item, target)
    if is_number(item) and is_number(target):
        return float(item) <= float(target)
    if isinstance(item, str) and isinstance(target, str):
        return item.lower() <= target.lower()
    return False


def matches_criteria(value: Value, criteria: Value) -> bool:
    if not isinstance(criteria, str):
        return same_value(value, criteria)
    found = CRITERIA.fullmatch(criteria)
    op, operand = (found.group(1) or "=", found.group(2)) if found else ("=", criteria)
    try:
        target: Value = float(operand)
    except ValueError:
        target = operand
    if op in ("=", "<>"):
        equal = (value is None or value == "") if operand == "" else same_value(value, target)
        return equal if op == "=" else not equal
    if not (is_number(value) and is_number(target)):
        return False
    a, b = float(value), float(target)
    return {"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]


def round_half_up(value: float, digits: int) -> float:
    quantum = Decimal(1).scaleb(-digits)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def round_down(value: float, digits: int) -> float:
    quantum = Decimal(1).scaleb(-digits)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_DOWN))


def excel_power(base: float, exponent: float, ref: str) -> float:
    if base == 0 and exponent < 0:
        raise FormulaError(f"#DIV/0! zero raised to a negative power in {ref}")
    if base < 0 and exponent != int(exponent):
        raise FormulaError(f"#NUM! negative number raised to a fractional power in {ref}")
    try:
        return float(base**exponent)
    except OverflowError as error:
        raise FormulaError(f"#NUM! power too large in {ref}") from error


def payment(rate: float, periods: float, present: float, future: float, due: int) -> float:
    if rate == 0:
        return -(present + future) / periods
    growth = (1 + rate) ** periods
    return -(rate * (present * growth + future)) / ((1 + rate * due) * (growth - 1))


def future_value(rate: float, periods: float, pmt: float, present: float, due: int) -> float:
    if rate == 0:
        return -(present + pmt * periods)
    growth = (1 + rate) ** periods
    return -(present * growth + pmt * (1 + rate * due) * (growth - 1) / rate)


def dated_npv(rate: float, flows: list[float], years: list[float]) -> float:
    return sum(flow / (1 + rate) ** year for flow, year in zip(flows, years))


def dated_irr(flows: list[float], years: list[float], guess: float) -> float | None:
    rate = guess
    for _ in range(100):
        value = dated_npv(rate, flows, years)
        slope = sum(-year * flow / (1 + rate) ** (year + 1) for flow, year in zip(flows, years))
        if slope == 0:
            break
        step = value / slope
        rate -= step
        if rate <= -1:
            break
        if abs(step) < 1e-12:
            return rate
    low, high = -0.999999, 1.0
    while dated_npv(high, flows, years) > 0 and high < 1e6:
        high *= 2
    if dated_npv(low, flows, years) * dated_npv(high, flows, years) > 0:
        return None
    for _ in range(300):
        middle = (low + high) / 2
        if dated_npv(low, flows, years) * dated_npv(middle, flows, years) <= 0:
            high = middle
        else:
            low = middle
    return (low + high) / 2


def flatten(values: list[Value | list[Value]]) -> Iterator[Value]:
    for value in values:
        if isinstance(value, list):
            yield from value
        else:
            yield value


def numbers(values: list[Value | list[Value]]) -> list[float]:
    return [float(v) for v in flatten(values) if isinstance(v, (int, float)) and not isinstance(v, bool)]


class Workbook:
    def __init__(self, cells: dict[str, CellContent], notes: dict[str, str] | None = None, sheets: list[str] | None = None, metadata: dict[str, CellMetadata] | None = None, names: dict[str, str] | None = None) -> None:
        self._cells = {normalize_ref(ref): content for ref, content in cells.items()}
        self._notes = {normalize_ref(ref): text for ref, text in (notes or {}).items()}
        self._sheets = sheets or list(dict.fromkeys(ref.rsplit("!", 1)[0] for ref in self._cells))
        self._metadata = {normalize_ref(ref): meta for ref, meta in (metadata or {}).items()}
        self._cache: dict[str, Value] = {}
        self._failures: dict[str, FormulaError] = {}
        self._evaluating: set[str] = set()
        self._dependents: dict[str, list[str]] | None = None
        self._rows: dict[str, dict[int, list[int]]] = {}
        self._label_counts: dict[str, dict[tuple[int, str], int]] = {}
        self._timelines: dict[str, list[tuple[int, dict[int, str]]]] = {}
        self._names = {name.upper(): text.lstrip("=") for name, text in (names or {}).items()}
        self._bounds: dict[str, tuple[int, int]] | None = None

    def bounds(self, sheet: str) -> tuple[int, int]:
        if self._bounds is None:
            found: dict[str, tuple[int, int]] = {}
            for ref in self._cells:
                name, address = split_ref(ref)
                rows, columns = found.get(name, (1, 1))
                found[name] = (max(rows, address.row), max(columns, address.column))
            self._bounds = found
        return self._bounds.get(sheet, (1, 1))

    def resolve(self, token: Token, base_sheet: str) -> Token:
        if token.kind != "name":
            return token
        target = self._names.get(token.text.upper())
        resolved = tokenize(target) if target else []
        if len(resolved) != 1 or resolved[0].kind not in ("ref", "span"):
            raise FormulaError(f"#NAME? {token.text} is not a defined range in {base_sheet}")
        return resolved[0]

    def span_reference(self, text: str, base_sheet: str) -> Reference:
        span = parse_span(text)
        sheet = span.sheet or base_sheet
        rows, columns = self.bounds(sheet)
        if span.rows:
            start, end = CellAddress(1, span.first, True, span.absolute_first), CellAddress(columns, min(span.last, MAX_ROWS), True, span.absolute_last)
        else:
            start, end = CellAddress(span.first, 1, span.absolute_first, True), CellAddress(min(span.last, MAX_COLUMNS), rows, span.absolute_last, True)
        return Reference(span.sheet, span.sheet_text, start, end)

    def reference_of(self, token: Token, base_sheet: str) -> Reference | None:
        token = self.resolve(token, base_sheet)
        if token.kind == "ref":
            return parse_reference(token.text)
        if token.kind == "span":
            return self.span_reference(token.text, base_sheet)
        return None

    @property
    def sheets(self) -> list[str]:
        return list(self._sheets)

    def cells(self) -> list[str]:
        return list(self._cells)

    def revision(self) -> str:
        content = "\n".join(f"{ref}={self._cells[ref]!r}" for ref in sorted(self._cells))
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def raw(self, ref: str) -> CellContent | None:
        return self._cells.get(normalize_ref(ref))

    def formula(self, ref: str) -> str | None:
        content = self.raw(ref)
        return content if isinstance(content, str) and content.startswith("=") else None

    def note(self, ref: str) -> str | None:
        return self._notes.get(normalize_ref(ref))

    def metadata_of(self, ref: str) -> CellMetadata:
        normalized = normalize_ref(ref)
        stored = self._metadata.get(normalized, {})
        return {
            "note": self._notes.get(normalized) or stored.get("note"),
            "font_color": stored.get("font_color"),
            "number_format": stored.get("number_format"),
        }

    def with_patch(self, ref: str, content: CellContent) -> "Workbook":
        cells = dict(self._cells)
        cells[normalize_ref(ref)] = content
        return Workbook(cells, self._notes, self._sheets, self._metadata)

    def value(self, ref: str) -> Value:
        ref = normalize_ref(ref)
        if ref in self._cache or self._evaluating:
            return self._evaluate(ref)
        try:
            return self._evaluate(ref)
        except RecursionError:
            self._evaluating.clear()
            self._warm(ref)
            return self._evaluate(ref)

    def _warm(self, ref: str) -> None:
        stack = [(ref, False)]
        seen: set[str] = set()
        while stack:
            cell, ready = stack.pop()
            if ready:
                try:
                    self._evaluate(cell)
                except (FormulaError, RecursionError):
                    self._evaluating.clear()
                continue
            if cell in seen or cell in self._cache or self.formula(cell) is None:
                continue
            seen.add(cell)
            stack.append((cell, True))
            stack.extend((precedent, False) for precedent in self.precedents(cell) if precedent not in seen)

    def _evaluate(self, ref: str) -> Value:
        if ref in self._cache:
            return self._cache[ref]
        if ref in self._failures:
            raise self._failures[ref]
        formula = self.formula(ref)
        if formula is None:
            return self._cells.get(ref)
        if ref in self._evaluating:
            raise CircularReferenceError(f"Circular reference through {ref}")
        self._evaluating.add(ref)
        try:
            result = FormulaEvaluator(self, ref, tokenize(formula)).evaluate()
        except FormulaError as error:
            self._failures[ref] = error
            raise
        finally:
            self._evaluating.discard(ref)
        self._cache[ref] = result
        return result

    def precedents(self, ref: str) -> list[str]:
        ref = normalize_ref(ref)
        formula = self.formula(ref)
        if formula is None:
            return []
        sheet = ref.rsplit("!", 1)[0]
        try:
            tokens = tokenize(formula)
        except FormulaError:
            return []
        found = []
        for token in tokens:
            if token.kind not in ("ref", "span", "name"):
                continue
            try:
                reference = self.reference_of(token, sheet)
            except FormulaError:
                continue
            found.extend(expand(reference, sheet))
        return list(dict.fromkeys(found))

    def all_precedents(self, ref: str) -> list[str]:
        return self._walk(normalize_ref(ref), self.precedents)

    def dependents(self, ref: str) -> list[str]:
        if self._dependents is None:
            index: dict[str, list[str]] = {}
            for cell in self._cells:
                for precedent in self.precedents(cell):
                    index.setdefault(precedent, []).append(cell)
            self._dependents = index
        return list(self._dependents.get(normalize_ref(ref), []))

    def all_dependents(self, ref: str) -> list[str]:
        return self._walk(normalize_ref(ref), self.dependents)

    def formula_pattern(self, ref: str) -> str | None:
        ref = normalize_ref(ref)
        formula = self.formula(ref)
        if formula is None:
            return None
        _, base = split_ref(ref)
        pieces = []
        for token in tokenize(formula):
            if token.kind == "span":
                span = parse_span(token.text)
                origin = base.row if span.rows else base.column
                part = lambda number, absolute: f"{number}" if absolute else f"[{number - origin}]"
                letter = "R" if span.rows else "C"
                pieces.append(f"{span.sheet_text}!" * bool(span.sheet_text) + f"{letter}{part(span.first, span.absolute_first)}:{letter}{part(span.last, span.absolute_last)}")
                continue
            if token.kind != "ref":
                pieces.append(token.text)
                continue
            reference = parse_reference(token.text)
            prefix = f"{reference.sheet_text}!" if reference.sheet_text else ""
            text = relative_part(reference.start, base)
            if reference.end is not None:
                text += ":" + relative_part(reference.end, base)
            pieces.append(prefix + text)
        return "=" + "".join(pieces)

    def shifted_formula(self, source_ref: str, target_ref: str) -> str | None:
        formula = self.formula(source_ref)
        if formula is None:
            return None
        _, source = split_ref(normalize_ref(source_ref))
        _, target = split_ref(normalize_ref(target_ref))
        delta_row = target.row - source.row
        delta_column = target.column - source.column
        pieces = []
        for token in tokenize(formula):
            if token.kind == "span":
                span = parse_span(token.text)
                delta = delta_row if span.rows else delta_column
                pieces.append(span_text(span, span.first if span.absolute_first else span.first + delta, span.last if span.absolute_last else span.last + delta))
                continue
            if token.kind != "ref":
                pieces.append(token.text)
                continue
            reference = parse_reference(token.text)
            prefix = f"{reference.sheet_text}!" if reference.sheet_text else ""
            text = shifted_part(reference.start, delta_row, delta_column)
            if reference.end is not None:
                text += ":" + shifted_part(reference.end, delta_row, delta_column)
            pieces.append(prefix + text)
        return "=" + "".join(pieces)

    def row_label(self, ref: str) -> str | None:
        sheet, address = split_ref(normalize_ref(ref))
        for column in range(1, address.column):
            content = self._cells.get(make_ref(sheet, CellAddress(column, address.row)))
            if is_label_text(content):
                return self._qualified_label(sheet, column, address.row, content)
        return None

    def column_header(self, ref: str) -> str | None:
        found = self._header(ref)
        return found[1] if found else None

    def header_row(self, ref: str) -> int | None:
        found = self._header(ref)
        return found[0] if found else None

    def _header(self, ref: str) -> tuple[int, str] | None:
        sheet, address = split_ref(normalize_ref(ref))
        block = self._timeline_above(sheet, address)
        if block:
            return block[0], block[1][address.column]
        for row in range(address.row - 1, 0, -1):
            content = self._cells.get(make_ref(sheet, CellAddress(address.column, row)))
            if is_label_text(content):
                return row, content
        return None

    def _sheet_rows(self, sheet: str) -> dict[int, list[int]]:
        if sheet not in self._rows:
            rows: dict[int, list[int]] = {}
            for ref in self._cells:
                cell_sheet, address = split_ref(ref)
                if cell_sheet == sheet:
                    rows.setdefault(address.row, []).append(address.column)
            self._rows[sheet] = {row: sorted(columns) for row, columns in rows.items()}
        return self._rows[sheet]

    def _number_at(self, ref: str) -> float | None:
        try:
            value = self.value(ref)
        except FormulaError:
            return None
        return float(value) if is_number(value) else None

    def _period_mark(self, ref: str) -> tuple[str, float, str] | None:
        raw = self._cells.get(ref)
        if isinstance(raw, str) and ISO_DATE.match(raw):
            return "date", to_serial(raw), raw[:10]
        number = self._number_at(ref)
        if number is None:
            return None
        number_format = (self._metadata.get(ref) or {}).get("number_format") or ""
        if DATE_FORMAT.search(number_format) and SERIAL_RANGE[0] <= number <= SERIAL_RANGE[1]:
            return "date", number, from_serial(number).isoformat()
        if not number.is_integer():
            return None
        if YEAR_RANGE[0] <= number <= YEAR_RANGE[1]:
            return "year", number, str(int(number))
        if PERIOD_INDEX_RANGE[0] <= number <= PERIOD_INDEX_RANGE[1]:
            return "index", number, f"Year {int(number)}"
        return None

    def _period_run(self, sheet: str, row: int, columns: list[int]) -> tuple[str, dict[int, str]] | None:
        marks = [(column, self._period_mark(make_ref(sheet, CellAddress(column, row)))) for column in columns]
        best: list[tuple[int, tuple[str, float, str]]] = []
        current: list[tuple[int, tuple[str, float, str]]] = []
        for column, mark in marks:
            follows = bool(current) and mark is not None and mark[0] == current[-1][1][0] and mark[1] > current[-1][1][1]
            if follows and mark[0] in ("index", "year") and mark[1] != current[-1][1][1] + 1:
                follows = False
            current = [*current, (column, mark)] if follows else ([(column, mark)] if mark is not None else [])
            if len(current) > len(best):
                best = current
        if len(best) < 3:
            return None
        periods = {column: mark[2] for column, mark in best}
        first, last = columns.index(best[0][0]), columns.index(best[-1][0])
        for position in (first - 1, last + 1):
            if 0 <= position < len(columns):
                content = self._cells.get(make_ref(sheet, CellAddress(columns[position], row)))
                if is_label_text(content) and PERIOD_WORDS.search(str(content)):
                    periods[columns[position]] = str(content).strip()
        return best[0][1][0], periods

    def _timeline(self, sheet: str) -> list[tuple[int, dict[int, str]]]:
        if sheet not in self._timelines:
            blocks: list[tuple[int, str, dict[int, str]]] = []
            for row, columns in sorted(self._sheet_rows(sheet).items()):
                found = self._period_run(sheet, row, columns)
                if found is None:
                    continue
                kind, periods = found
                if blocks and row - blocks[-1][0] <= STACKED_HEADER_ROWS:
                    if PERIOD_PRIORITY[kind] < PERIOD_PRIORITY[blocks[-1][1]]:
                        blocks[-1] = (row, kind, periods)
                    continue
                blocks.append((row, kind, periods))
            self._timelines[sheet] = [(row, periods) for row, _, periods in blocks]
        return self._timelines[sheet]

    def _timeline_above(self, sheet: str, address: CellAddress) -> tuple[int, dict[int, str]] | None:
        above = [block for block in self._timeline(sheet) if block[0] < address.row]
        if not above or address.column not in above[-1][1]:
            return None
        return above[-1]

    def timelines(self, sheet: str) -> list[tuple[int, dict[int, str]]]:
        return list(self._timeline(sheet))

    def in_timeline(self, ref: str) -> bool:
        sheet, address = split_ref(normalize_ref(ref))
        return self._timeline_above(sheet, address) is not None

    def _qualified_label(self, sheet: str, column: int, row: int, label: str) -> str:
        if sheet not in self._label_counts:
            counts: dict[tuple[int, str], int] = {}
            for cell_row, columns in self._sheet_rows(sheet).items():
                for cell_column in columns:
                    content = self._cells[make_ref(sheet, CellAddress(cell_column, cell_row))]
                    if is_label_text(content):
                        counts[(cell_column, content)] = counts.get((cell_column, content), 0) + 1
            self._label_counts[sheet] = counts
        if self._label_counts[sheet].get((column, label), 0) < 2:
            return label
        rows = self._sheet_rows(sheet)
        for above in range(row - 1, 0, -1):
            title = self._cells.get(make_ref(sheet, CellAddress(column, above)))
            if not is_label_text(title):
                continue
            numbers_right = [c for c in rows.get(above, []) if c > column and self._number_at(make_ref(sheet, CellAddress(c, above))) is not None]
            if not numbers_right:
                return f"{title} – {label}"
        return label

    @staticmethod
    def _walk(start: str, neighbours: Callable[[str], list[str]]) -> list[str]:
        seen: dict[str, None] = {}
        queue = deque(neighbours(start))
        while queue:
            cell = queue.popleft()
            if cell in seen or cell == start:
                continue
            seen[cell] = None
            queue.extend(neighbours(cell))
        return list(seen)


class FormulaEvaluator:
    def __init__(self, book: Workbook, ref: str, tokens: list[Token]) -> None:
        self.book = book
        self.ref = ref
        self.sheet = ref.rsplit("!", 1)[0]
        self.tokens = tokens
        self.position = 0

    def evaluate(self) -> Value:
        result = self.comparison()
        if self.position != len(self.tokens):
            raise UnsupportedFormulaError(f"Unexpected {self.tokens[self.position].text!r} in {self.ref}")
        if isinstance(result, list):
            raise UnsupportedFormulaError(f"A range cannot be the result of {self.ref}")
        return result

    def peek(self) -> Token | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self) -> Token:
        token = self.peek()
        if token is None:
            raise UnsupportedFormulaError(f"Formula in {self.ref} ends too early")
        self.position += 1
        return token

    def expect(self, kind: str) -> None:
        token = self.take()
        if token.kind != kind:
            raise UnsupportedFormulaError(f"Expected {kind} but found {token.text!r} in {self.ref}")

    def at_op(self, *ops: str) -> bool:
        token = self.peek()
        return token is not None and token.kind == "op" and token.text in ops

    def comparison(self) -> Value:
        left = self.concatenation()
        while self.at_op("=", "<>", "<", ">", "<=", ">="):
            op = self.take().text
            right = self.concatenation()
            left = self.compare(op, left, right)
        return left

    def concatenation(self) -> Value:
        left = self.additive()
        while self.at_op("&"):
            self.take()
            right = self.additive()
            left = f"{'' if left is None else left}{'' if right is None else right}"
        return left

    def additive(self) -> Value:
        left = self.term()
        while self.at_op("+", "-"):
            op = self.take().text
            right = self.term()
            left = self.number(left) + self.number(right) if op == "+" else self.number(left) - self.number(right)
        return left

    def term(self) -> Value:
        left = self.power()
        while self.at_op("*", "/"):
            op = self.take().text
            right = self.power()
            if op == "*":
                left = self.number(left) * self.number(right)
            else:
                divisor = self.number(right)
                if divisor == 0:
                    raise FormulaError(f"Division by zero in {self.ref}")
                left = self.number(left) / divisor
        return left

    def power(self) -> Value:
        left = self.unary()
        while self.at_op("^"):
            self.take()
            right = self.unary()
            left = excel_power(self.number(left), self.number(right), self.ref)
        return left

    def unary(self) -> Value:
        if self.at_op("-"):
            self.take()
            return -self.number(self.unary())
        if self.at_op("+"):
            self.take()
            return self.number(self.unary())
        return self.primary()

    def primary(self) -> Value | list[Value]:
        token = self.take()
        if token.kind == "number":
            return float(token.text[:-1]) / 100 if token.text.endswith("%") else float(token.text)
        if token.kind == "string":
            return token.text[1:-1].replace('""', '"')
        if token.kind == "bool":
            return token.text == "TRUE"
        if token.kind == "error":
            raise FormulaError(f"{token.text[token.text.index('#'):]} written in the formula in {self.ref}")
        if token.kind in ("ref", "span", "name"):
            reference = self.book.reference_of(token, self.sheet)
            values = [self.book.value(cell) for cell in expand(reference, self.sheet)]
            if reference.end is None:
                return values[0]
            return Grid(values, abs(reference.end.column - reference.start.column) + 1)
        if token.kind == "func":
            name = token.text.upper()
            for prefix in FUNCTION_PREFIXES:
                name = name.removeprefix(prefix)
            return self.function(name)
        if token.kind == "lparen":
            value = self.comparison()
            self.expect("rparen")
            return value
        raise UnsupportedFormulaError(f"Unexpected {token.text!r} in {self.ref}")

    def function(self, name: str) -> Value:
        if name not in SUPPORTED_FUNCTIONS:
            raise UnsupportedFormulaError(f"Unsupported function {name} in {self.ref}; supported: {', '.join(SUPPORTED_FUNCTIONS)}")
        self.expect("lparen")
        arguments: list[Value | list[Value] | Failure] = []
        if not (self.peek() and self.peek().kind == "rparen"):
            arguments.append(self.argument())
            while self.peek() and self.peek().kind == "comma":
                self.take()
                arguments.append(self.argument())
        self.expect("rparen")
        if name == "IFERROR":
            return self.settled(arguments[1]) if isinstance(arguments[0], Failure) else arguments[0]
        if name in INFORMATION_FUNCTIONS:
            return self.information(name, arguments[0] if arguments else None)
        if name == "CHOOSE":
            index = int(self.number(self.settled(arguments[0])))
            if not 1 <= index < len(arguments):
                raise FormulaError(f"#VALUE! CHOOSE index {index} has no value in {self.ref}")
            return self.settled(arguments[index])
        if name == "IF":
            condition = self.settled(arguments[0])
            if condition:
                return self.settled(arguments[1]) if len(arguments) > 1 else True
            return self.settled(arguments[2]) if len(arguments) > 2 else False
        values = [self.settled(argument) for argument in arguments]
        try:
            return getattr(self, f"call_{name.lower().replace('.', '_')}")(values)
        except (IndexError, TypeError, ValueError, OverflowError, ZeroDivisionError) as error:
            raise FormulaError(f"#VALUE! {name} cannot be calculated with these arguments in {self.ref}") from error

    def information(self, name: str, argument: Value | list[Value] | Failure) -> Value:
        if isinstance(argument, Failure):
            return name == "ISERROR"
        if isinstance(argument, list):
            argument = argument[0] if argument else None
        if name == "ISERROR":
            return False
        if name == "ISNUMBER":
            return is_number(argument)
        if name == "ISTEXT":
            return isinstance(argument, str) and not ISO_DATE.match(argument)
        return argument is None

    def argument(self) -> Value | list[Value] | Failure:
        if self.peek() is not None and self.peek().kind in ("comma", "rparen"):
            return None
        start = self.position
        try:
            return self.comparison()
        except (UnsupportedFormulaError, CircularReferenceError):
            raise
        except FormulaError as error:
            self.skip_argument(start)
            return Failure(error)

    def skip_argument(self, start: int) -> None:
        self.position = start
        depth = 0
        while self.peek() is not None:
            kind = self.peek().kind
            if depth == 0 and kind in ("comma", "rparen"):
                return
            depth += 1 if kind == "lparen" else -1 if kind == "rparen" else 0
            self.position += 1

    def settled(self, argument: Value | list[Value] | Failure) -> Value | list[Value]:
        if isinstance(argument, Failure):
            raise argument.error
        return argument

    def call_sum(self, values: list) -> Value:
        return sum(numbers(values))

    def call_average(self, values: list) -> Value:
        found = numbers(values)
        if not found:
            raise FormulaError(f"AVERAGE of no numbers in {self.ref}")
        return sum(found) / len(found)

    def call_min(self, values: list) -> Value:
        return min(numbers(values), default=0.0)

    def call_max(self, values: list) -> Value:
        return max(numbers(values), default=0.0)

    def call_abs(self, values: list) -> Value:
        return abs(self.number(values[0]))

    def call_round(self, values: list) -> Value:
        return round_half_up(self.number(values[0]), int(self.number(values[1])))

    def call_and(self, values: list) -> Value:
        return all(bool(v) for v in flatten(values) if v is not None and not isinstance(v, str))

    def call_or(self, values: list) -> Value:
        return any(bool(v) for v in flatten(values) if v is not None and not isinstance(v, str))

    def call_not(self, values: list) -> Value:
        return not bool(values[0])

    def call_sumif(self, values: list) -> Value:
        checked = self.cells_of(values[0])
        summed = self.cells_of(values[2]) if len(values) > 2 and values[2] is not None else checked
        if len(summed) != len(checked):
            raise FormulaError(f"SUMIF ranges have different sizes in {self.ref}")
        return sum(float(total) for value, total in zip(checked, summed) if matches_criteria(value, values[1]) and is_number(total))

    def call_sumifs(self, values: list) -> Value:
        summed = self.cells_of(values[0])
        selected = self.rows_meeting(values[1:], len(summed), "SUMIFS")
        return sum(float(summed[i]) for i in selected if is_number(summed[i]))

    def call_countif(self, values: list) -> Value:
        return float(sum(1 for value in self.cells_of(values[0]) if matches_criteria(value, values[1])))

    def call_countifs(self, values: list) -> Value:
        size = len(self.cells_of(values[0])) if values else 0
        return float(len(self.rows_meeting(values, size, "COUNTIFS")))

    def rows_meeting(self, pairs: list, size: int, name: str) -> list[int]:
        if len(pairs) % 2:
            raise FormulaError(f"{name} needs criteria in range and value pairs in {self.ref}")
        selected = list(range(size))
        for criteria_range, criteria in zip(pairs[::2], pairs[1::2]):
            cells = self.cells_of(criteria_range)
            if len(cells) != size:
                raise FormulaError(f"{name} ranges have different sizes in {self.ref}")
            selected = [i for i in selected if matches_criteria(cells[i], criteria)]
        return selected

    def call_sumproduct(self, values: list) -> Value:
        arrays = [self.cells_of(value) for value in values]
        if len({len(array) for array in arrays}) != 1:
            raise FormulaError(f"SUMPRODUCT ranges have different sizes in {self.ref}")
        total = 0.0
        for items in zip(*arrays):
            product = 1.0
            for item in items:
                product *= float(item) if is_number(item) else 0.0
            total += product
        return total

    def call_index(self, values: list) -> Value:
        grid = self.grid_of(values[0])
        row = int(self.number(values[1]))
        column = int(self.number(values[2])) if len(values) > 2 and values[2] is not None else None
        if column is None:
            row, column = (row, 1) if grid.width == 1 else (1, row) if grid.height == 1 else (row, None)
        if column is None:
            raise UnsupportedFormulaError(f"INDEX on a table needs a row and a column in {self.ref}")
        if not (1 <= row <= grid.height and 1 <= column <= grid.width):
            raise FormulaError(f"#REF: INDEX position outside the range in {self.ref}")
        return grid.at(row, column)

    def call_match(self, values: list) -> Value:
        mode = int(self.number(values[2])) if len(values) > 2 and values[2] is not None else 1
        return float(self.position_of(values[0], self.line_of(values[1]), mode))

    def call_vlookup(self, values: list) -> Value:
        table = self.grid_of(values[1])
        column = int(self.number(values[2]))
        approximate = bool(values[3]) if len(values) > 3 and values[3] is not None else True
        if not 1 <= column <= table.width:
            raise FormulaError(f"#REF: VLOOKUP column {column} is outside the table in {self.ref}")
        row = self.position_of(values[0], table.column(1), 1 if approximate else 0)
        return table.at(row, column)

    def call_xlookup(self, values: list) -> Value:
        mode = int(self.number(values[4])) if len(values) > 4 and values[4] is not None else 0
        if mode != 0:
            raise UnsupportedFormulaError(f"XLOOKUP supports exact match only in {self.ref}")
        lookup, results = self.line_of(values[1]), self.line_of(values[2])
        if len(lookup) != len(results):
            raise FormulaError(f"XLOOKUP ranges have different sizes in {self.ref}")
        try:
            return results[self.position_of(values[0], lookup, 0) - 1]
        except FormulaError:
            if len(values) > 3 and values[3] is not None:
                return values[3]
            raise

    def call_year(self, values: list) -> Value:
        return float(from_serial(to_serial(values[0])).year)

    def call_month(self, values: list) -> Value:
        return float(from_serial(to_serial(values[0])).month)

    def call_day(self, values: list) -> Value:
        return float(from_serial(to_serial(values[0])).day)

    def call_date(self, values: list) -> Value:
        year, month, day = (int(self.number(v)) for v in values[:3])
        first = shift_months(date(year, 1, 1), month - 1)
        return float((first + timedelta(days=day - 1) - EXCEL_EPOCH).days)

    def call_edate(self, values: list) -> Value:
        return float((shift_months(from_serial(to_serial(values[0])), int(self.number(values[1]))) - EXCEL_EPOCH).days)

    def call_npv(self, values: list) -> Value:
        rate = self.number(values[0])
        return sum(value / (1 + rate) ** period for period, value in enumerate(numbers(values[1:]), start=1))

    def call_xnpv(self, values: list) -> Value:
        rate = self.number(values[0])
        flows = self.cells_of(values[1])
        days = [to_serial(day) for day in self.cells_of(values[2])]
        if len(flows) != len(days) or not days:
            raise FormulaError(f"XNPV needs one date per cash flow in {self.ref}")
        return sum(self.number(flow) / (1 + rate) ** ((day - days[0]) / 365) for flow, day in zip(flows, days))

    def call_power(self, values: list) -> Value:
        return excel_power(self.number(values[0]), self.number(values[1]), self.ref)

    def call_rounddown(self, values: list) -> Value:
        return round_down(self.number(values[0]), int(self.number(values[1])))

    def call_int(self, values: list) -> Value:
        return float(math.floor(self.number(values[0])))

    def call_mod(self, values: list) -> Value:
        number, divisor = self.number(values[0]), self.number(values[1])
        if divisor == 0:
            raise FormulaError(f"#DIV/0! MOD by zero in {self.ref}")
        return number - divisor * math.floor(number / divisor)

    def call_ppmt(self, values: list) -> Value:
        rate, period, periods, present = (self.number(v) for v in values[:4])
        future = self.number(values[4]) if len(values) > 4 and values[4] is not None else 0.0
        due = 1 if len(values) > 5 and values[5] is not None and self.number(values[5]) else 0
        if not 1 <= period <= periods:
            raise FormulaError(f"#NUM! PPMT period {period:g} is outside 1 to {periods:g} in {self.ref}")
        pmt = payment(rate, periods, present, future, due)
        if due and period == 1:
            return pmt
        interest = future_value(rate, period - 1, pmt, present, due) * rate
        return pmt - (interest / (1 + rate) if due else interest)

    def call_xirr(self, values: list) -> Value:
        flows = [self.number(flow) for flow in self.cells_of(values[0])]
        days = [to_serial(day) for day in self.cells_of(values[1])]
        if len(flows) != len(days) or not days:
            raise FormulaError(f"#NUM! XIRR needs one date per cash flow in {self.ref}")
        if not (any(flow > 0 for flow in flows) and any(flow < 0 for flow in flows)):
            raise FormulaError(f"#NUM! XIRR needs at least one positive and one negative cash flow in {self.ref}")
        guess = self.number(values[2]) if len(values) > 2 and values[2] is not None else 0.1
        rate = dated_irr(flows, [(day - days[0]) / 365 for day in days], guess)
        if rate is None:
            raise FormulaError(f"#NUM! XIRR found no rate that sets the cash flows to zero in {self.ref}")
        return rate

    def call_pmt(self, values: list) -> Value:
        rate, periods, present = (self.number(v) for v in values[:3])
        future = self.number(values[3]) if len(values) > 3 and values[3] is not None else 0.0
        due = 1 if len(values) > 4 and values[4] is not None and self.number(values[4]) else 0
        return payment(rate, periods, present, future, due)

    def call_irr(self, values: list) -> Value:
        flows = numbers(values[:1])
        if not (any(flow > 0 for flow in flows) and any(flow < 0 for flow in flows)):
            raise FormulaError(f"#NUM! IRR needs at least one positive and one negative cash flow in {self.ref}")
        guess = self.number(values[1]) if len(values) > 1 and values[1] is not None else 0.1
        rate = dated_irr(flows, [float(period) for period in range(len(flows))], guess)
        if rate is None:
            raise FormulaError(f"#NUM! IRR found no rate that sets the cash flows to zero in {self.ref}")
        return rate

    def call_hlookup(self, values: list) -> Value:
        table = self.grid_of(values[1])
        row = int(self.number(values[2]))
        approximate = bool(values[3]) if len(values) > 3 and values[3] is not None else True
        if not 1 <= row <= table.height:
            raise FormulaError(f"#REF: HLOOKUP row {row} is outside the table in {self.ref}")
        column = self.position_of(values[0], table.row(1), 1 if approximate else 0)
        return table.at(row, column)

    def call_count(self, values: list) -> Value:
        return float(sum(1 for v in flatten(values) if is_number(v) or (isinstance(v, str) and ISO_DATE.match(v))))

    def call_counta(self, values: list) -> Value:
        return float(sum(1 for v in flatten(values) if v is not None and v != ""))

    def call_large(self, values: list) -> Value:
        return self.ranked(values, reverse=True)

    def call_small(self, values: list) -> Value:
        return self.ranked(values, reverse=False)

    def ranked(self, values: list, reverse: bool) -> Value:
        found = sorted(numbers(values[:1]), reverse=reverse)
        position = int(self.number(values[1]))
        if not 1 <= position <= len(found):
            raise FormulaError(f"#NUM! position {position} is outside the {len(found)} numbers in {self.ref}")
        return found[position - 1]

    def call_exp(self, values: list) -> Value:
        try:
            return math.exp(self.number(values[0]))
        except OverflowError as error:
            raise FormulaError(f"#NUM! EXP too large in {self.ref}") from error

    def call_ln(self, values: list) -> Value:
        number = self.number(values[0])
        if number <= 0:
            raise FormulaError(f"#NUM! LN of a number that is not positive in {self.ref}")
        return math.log(number)

    def call_normsdist(self, values: list) -> Value:
        return 0.5 * (1 + math.erf(self.number(values[0]) / math.sqrt(2)))

    def call_norm_s_dist(self, values: list) -> Value:
        z = self.number(values[0])
        if len(values) > 1 and values[1] is not None and not values[1]:
            return math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
        return self.call_normsdist(values[:1])

    def call_eomonth(self, values: list) -> Value:
        start = from_serial(to_serial(values[0]))
        return float((end_of_month(start, int(self.number(values[1]))) - EXCEL_EPOCH).days)

    def position_of(self, target: Value, line: list[Value], mode: int) -> int:
        if mode == 0:
            for index, item in enumerate(line, start=1):
                if same_value(item, target):
                    return index
        elif mode == 1:
            found = 0
            for index, item in enumerate(line, start=1):
                if item is None:
                    continue
                if not not_greater(item, target):
                    break
                found = index
            if found:
                return found
        else:
            raise UnsupportedFormulaError(f"Match type {mode} is not supported in {self.ref}")
        raise FormulaError(f"#N/A: {target!r} not found in {self.ref}")

    def cells_of(self, value: Value | list[Value]) -> list[Value]:
        return list(value) if isinstance(value, list) else [value]

    def grid_of(self, value: Value | list[Value]) -> Grid:
        return value if isinstance(value, Grid) else Grid(self.cells_of(value), 1)

    def line_of(self, value: Value | list[Value]) -> list[Value]:
        grid = self.grid_of(value)
        if grid.width != 1 and grid.height != 1:
            raise UnsupportedFormulaError(f"A lookup range must be one row or one column in {self.ref}")
        return list(grid)

    def number(self, value: Value | list[Value]) -> float:
        if value is None:
            return 0.0
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, list):
            raise UnsupportedFormulaError(f"A range is used where a single value is needed in {self.ref}")
        if isinstance(value, str) and ISO_DATE.match(value):
            return to_serial(value)
        raise FormulaError(f"Text {value!r} used as a number in {self.ref}")

    def compare(self, op: str, left: Value, right: Value) -> bool:
        if isinstance(left, str) or isinstance(right, str):
            a, b = str(left).lower(), str(right).lower()
        else:
            a, b = self.number(left), self.number(right)
        return {"=": a == b, "<>": a != b, "<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]
