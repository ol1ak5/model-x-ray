import re
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CellContent = float | str | bool
Value = float | str | bool | None

TOKEN_PATTERN = re.compile(
    r"""
    (?P<ws>\s+)
    |(?P<string>"(?:[^"]|"")*")
    |(?P<func>[A-Za-z_][A-Za-z0-9_.]*(?=\())
    |(?P<ref>(?:(?:'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_&.]*)!)?\$?[A-Za-z]{1,3}\$?[0-9]+(?::\$?[A-Za-z]{1,3}\$?[0-9]+)?)
    |(?P<number>[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?%?)
    |(?P<bool>TRUE|FALSE)
    |(?P<op><=|>=|<>|[-+*/^&=<>])
    |(?P<lparen>\()
    |(?P<rparen>\))
    |(?P<comma>,)
    """,
    re.VERBOSE,
)

CELL_PATTERN = re.compile(r"(\$?)([A-Za-z]{1,3})(\$?)([0-9]+)")

SUPPORTED_FUNCTIONS = ("SUM", "AVERAGE", "MIN", "MAX", "IF", "ROUND", "ABS")


class FormulaError(Exception):
    pass


class UnsupportedFormulaError(FormulaError):
    pass


class CircularReferenceError(FormulaError):
    pass


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


def tokenize(formula: str) -> list[Token]:
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


def round_half_up(value: float, digits: int) -> float:
    quantum = Decimal(1).scaleb(-digits)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def flatten(values: list[Value | list[Value]]) -> Iterator[Value]:
    for value in values:
        if isinstance(value, list):
            yield from value
        else:
            yield value


def numbers(values: list[Value | list[Value]]) -> list[float]:
    return [float(v) for v in flatten(values) if isinstance(v, (int, float)) and not isinstance(v, bool)]


class Workbook:
    def __init__(self, cells: dict[str, CellContent], notes: dict[str, str] | None = None, sheets: list[str] | None = None) -> None:
        self._cells = {normalize_ref(ref): content for ref, content in cells.items()}
        self._notes = {normalize_ref(ref): text for ref, text in (notes or {}).items()}
        self._sheets = sheets or list(dict.fromkeys(ref.rsplit("!", 1)[0] for ref in self._cells))
        self._cache: dict[str, Value] = {}
        self._evaluating: set[str] = set()
        self._dependents: dict[str, list[str]] | None = None

    @property
    def sheets(self) -> list[str]:
        return list(self._sheets)

    def cells(self) -> list[str]:
        return list(self._cells)

    def raw(self, ref: str) -> CellContent | None:
        return self._cells.get(normalize_ref(ref))

    def formula(self, ref: str) -> str | None:
        content = self.raw(ref)
        return content if isinstance(content, str) and content.startswith("=") else None

    def note(self, ref: str) -> str | None:
        return self._notes.get(normalize_ref(ref))

    def with_patch(self, ref: str, content: CellContent) -> "Workbook":
        cells = dict(self._cells)
        cells[normalize_ref(ref)] = content
        return Workbook(cells, self._notes, self._sheets)

    def value(self, ref: str) -> Value:
        ref = normalize_ref(ref)
        if ref in self._cache:
            return self._cache[ref]
        formula = self.formula(ref)
        if formula is None:
            return self._cells.get(ref)
        if ref in self._evaluating:
            raise CircularReferenceError(f"Circular reference through {ref}")
        self._evaluating.add(ref)
        try:
            result = FormulaEvaluator(self, ref, tokenize(formula)).evaluate()
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
        found = [cell for token in tokenize(formula) if token.kind == "ref" for cell in expand(parse_reference(token.text), sheet)]
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

    def row_label(self, ref: str) -> str | None:
        sheet, address = split_ref(normalize_ref(ref))
        for column in range(1, address.column):
            content = self._cells.get(make_ref(sheet, CellAddress(column, address.row)))
            if isinstance(content, str) and not content.startswith("="):
                return content
        return None

    def column_header(self, ref: str) -> str | None:
        sheet, address = split_ref(normalize_ref(ref))
        for row in range(address.row - 1, 0, -1):
            content = self._cells.get(make_ref(sheet, CellAddress(address.column, row)))
            if isinstance(content, str) and not content.startswith("="):
                return content
        return None

    @staticmethod
    def _walk(start: str, neighbours: Callable[[str], list[str]]) -> list[str]:
        seen: list[str] = []
        queue = deque(neighbours(start))
        while queue:
            cell = queue.popleft()
            if cell in seen or cell == start:
                continue
            seen.append(cell)
            queue.extend(neighbours(cell))
        return seen


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
            left = self.number(left) ** self.number(right)
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
        if token.kind == "ref":
            cells = expand(parse_reference(token.text), self.sheet)
            values = [self.book.value(cell) for cell in cells]
            return values if parse_reference(token.text).end is not None else values[0]
        if token.kind == "func":
            return self.function(token.text.upper())
        if token.kind == "lparen":
            value = self.comparison()
            self.expect("rparen")
            return value
        raise UnsupportedFormulaError(f"Unexpected {token.text!r} in {self.ref}")

    def function(self, name: str) -> Value:
        if name not in SUPPORTED_FUNCTIONS:
            raise UnsupportedFormulaError(f"Unsupported function {name} in {self.ref}; supported: {', '.join(SUPPORTED_FUNCTIONS)}")
        self.expect("lparen")
        arguments: list[Value | list[Value]] = []
        if not (self.peek() and self.peek().kind == "rparen"):
            arguments.append(self.comparison())
            while self.peek() and self.peek().kind == "comma":
                self.take()
                arguments.append(self.comparison())
        self.expect("rparen")
        if name == "SUM":
            return sum(numbers(arguments))
        if name == "AVERAGE":
            values = numbers(arguments)
            if not values:
                raise FormulaError(f"AVERAGE of no numbers in {self.ref}")
            return sum(values) / len(values)
        if name == "MIN":
            return min(numbers(arguments), default=0.0)
        if name == "MAX":
            return max(numbers(arguments), default=0.0)
        if name == "ABS":
            return abs(self.number(arguments[0]))
        if name == "ROUND":
            return round_half_up(self.number(arguments[0]), int(self.number(arguments[1])))
        condition = arguments[0]
        if condition:
            return arguments[1] if len(arguments) > 1 else True
        return arguments[2] if len(arguments) > 2 else False

    def number(self, value: Value | list[Value]) -> float:
        if value is None:
            return 0.0
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, list):
            raise UnsupportedFormulaError(f"A range is used where a single value is needed in {self.ref}")
        raise FormulaError(f"Text {value!r} used as a number in {self.ref}")

    def compare(self, op: str, left: Value, right: Value) -> bool:
        if isinstance(left, str) or isinstance(right, str):
            a, b = str(left).lower(), str(right).lower()
        else:
            a, b = self.number(left), self.number(right)
        return {"=": a == b, "<>": a != b, "<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]
