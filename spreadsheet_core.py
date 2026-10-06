import re
from collections import defaultdict


def col_to_index(col_name: str) -> int:
    col_name = col_name.upper()
    idx = 0
    for ch in col_name:
        idx = idx * 26 + (ord(ch) - 64)
    return idx - 1


def index_to_col(index: int) -> str:
    index += 1
    letters = []
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters.append(chr(65 + rem))
    return ''.join(reversed(letters))


def cell_ref_to_rc(ref: str):
    match = re.match(r'^\s*([A-Za-z]+)(\d+)\s*$', ref)
    if not match:
        return None
    col = col_to_index(match.group(1))
    row = int(match.group(2)) - 1
    return row, col


def rc_to_cell(row: int, col: int) -> str:
    return f"{index_to_col(col)}{row + 1}"


class SheetModel:
    def __init__(self, rows=50, cols=20):
        self.rows = rows
        self.cols = cols
        self.cells = {}
        self.styles = {}

    def clear(self):
        self.cells.clear()
        self.styles.clear()

    def set_cell(self, row, col, value):
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return
        if value in ('', None):
            self.cells.pop(f"{row}:{col}", None)
            self.styles.pop(f"{row}:{col}", None)
            return
        self.cells[f"{row}:{col}"] = str(value)

    def get_cell(self, row, col):
        return self.cells.get(f"{row}:{col}", '')

    def cell_value(self, ref_or_row, col=None):
        if isinstance(ref_or_row, str):
            pos = cell_ref_to_rc(ref_or_row)
            if pos is None:
                return ''
            row, col = pos
        else:
            row = ref_or_row
        return self.get_cell(row, col)

    def load_from_dict(self, payload):
        if 'cells' in payload:
            self.cells = payload['cells']
        if 'styles' in payload:
            self.styles = payload['styles']
        if 'rows' in payload:
            self.rows = int(payload['rows'])
        if 'cols' in payload:
            self.cols = int(payload['cols'])

    def to_dict(self):
        return {
            'rows': self.rows,
            'cols': self.cols,
            'cells': self.cells,
            'styles': self.styles,
        }

    def to_matrix(self):
        matrix = [['' for _ in range(self.cols)] for _ in range(self.rows)]
        for key, value in self.cells.items():
            try:
                row, col = map(int, key.split(':'))
                matrix[row][col] = self.evaluate_cell(row, col)
            except ValueError:
                continue
        return matrix

    def export_csv(self, file_obj):
        rows = self.to_matrix()
        for row in rows:
            file_obj.write(','.join(self._csv_escape(v) for v in row) + '\n')

    def _csv_escape(self, value):
        value = str(value)
        if ',' in value or '"' in value or '\n' in value:
            value = '"' + value.replace('"', '""') + '"'
        return value

    def load_csv(self, text):
        self.clear()
        lines = [line for line in text.splitlines() if line.strip()]
        rows = []
        for line in lines:
            cells = []
            current = ''
            in_quotes = False
            i = 0
            while i < len(line):
                ch = line[i]
                if ch == '"':
                    if in_quotes and i + 1 < len(line) and line[i + 1] == '"':
                        current += '"'
                        i += 1
                    else:
                        in_quotes = not in_quotes
                elif ch == ',' and not in_quotes:
                    cells.append(current)
                    current = ''
                else:
                    current += ch
                i += 1
            cells.append(current)
            rows.append(cells)

        max_cols = max((len(r) for r in rows), default=0)
        max_rows = len(rows)
        self.rows = max_rows
        self.cols = max_cols
        for r, row in enumerate(rows):
            for c, value in enumerate(row[:self.cols]):
                if value != '':
                    self.set_cell(r, c, value)

    def get_display_value(self, row, col):
        value = self.get_cell(row, col)
        if value == '':
            return ''
        if str(value).startswith('='):
            try:
                return str(self.evaluate_formula(value, row, col))
            except Exception:
                return '#ERROR'
        return value

    def evaluate_cell(self, row, col):
        value = self.get_cell(row, col)
        if value == '':
            return ''
        if str(value).startswith('='):
            try:
                return self.evaluate_formula(value, row, col)
            except Exception:
                return '#ERROR'
        return value

    def evaluate_formula(self, formula, row, col):
        expr = formula[1:].strip()
        if not expr:
            return ''

        # Handle function calls first.
        func_match = re.match(r'^([A-Z_]+)\s*\((.*)\)\s*$', expr, re.I)
        if func_match:
            name = func_match.group(1).upper()
            args_text = func_match.group(2).strip()
            args = split_args(args_text)
            evaluated = [self._evaluate_arg(arg, row, col) for arg in args]
            return self._call_function(name, evaluated, row, col)

        # Fallback: arithmetic expression evaluation.
        return self._evaluate_arithmetic(expr, row, col)

    def _evaluate_arg(self, text, row, col):
        text = text.strip()
        if not text:
            return ''
        if text.startswith('='):
            return self.evaluate_formula(text, row, col)

        # Range argument handling.
        if ':' in text:
            start_ref, end_ref = [part.strip() for part in text.split(':', 1)]
            start = cell_ref_to_rc(start_ref)
            end = cell_ref_to_rc(end_ref)
            if start and end:
                result = []
                r1, c1 = start
                r2, c2 = end
                for rr in range(min(r1, r2), max(r1, r2) + 1):
                    for cc in range(min(c1, c2), max(c1, c2) + 1):
                        result.append(self.evaluate_cell(rr, cc))
                return result

        # Cell reference handling.
        if re.fullmatch(r'[A-Za-z]+\d+', text):
            ref = text.upper()
            pos = cell_ref_to_rc(ref)
            if pos:
                return self.evaluate_cell(*pos)

        # Numeric / string literal.
        if re.fullmatch(r'-?\d+(?:\.\d+)?', text):
            return float(text)

        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]

        return text

    def _call_function(self, name, args, row, col):
        if name == 'SUM':
            flat = flatten_list(args)
            nums = [float(v) for v in flat if self._is_number(v)]
            return sum(nums)
        if name == 'AVERAGE':
            flat = flatten_list(args)
            nums = [float(v) for v in flat if self._is_number(v)]
            return sum(nums) / len(nums) if nums else 0
        if name == 'MIN':
            flat = flatten_list(args)
            nums = [float(v) for v in flat if self._is_number(v)]
            return min(nums) if nums else 0
        if name == 'MAX':
            flat = flatten_list(args)
            nums = [float(v) for v in flat if self._is_number(v)]
            return max(nums) if nums else 0
        if name == 'COUNT':
            flat = flatten_list(args)
            return sum(1 for v in flat if self._is_number(v))
        if name == 'COUNTA':
            flat = flatten_list(args)
            return sum(1 for v in flat if v not in ('', None))
        if name == 'IF':
            if len(args) >= 3:
                condition = args[0]
                return args[1] if self._truthy(condition) else args[2]
            return ''
        if name == 'AND':
            return all(self._truthy(v) for v in flatten_list(args))
        if name == 'OR':
            return any(self._truthy(v) for v in flatten_list(args))
        if name == 'NOT':
            return not self._truthy(args[0]) if args else False
        if name == 'ABS':
            return abs(float(args[0])) if args and self._is_number(args[0]) else 0
        if name == 'ROUND':
            if len(args) >= 2:
                return round(float(args[0]), int(float(args[1])))
            return round(float(args[0])) if args else 0
        if name == 'LEN':
            return len(str(args[0])) if args else 0
        if name == 'UPPER':
            return str(args[0]).upper() if args else ''
        if name == 'LOWER':
            return str(args[0]).lower() if args else ''
        if name == 'CONCAT':
            return ''.join(str(v) for v in flatten_list(args))
        if name == 'TODAY':
            from datetime import date
            return date.today().isoformat()
        if name == 'NOW':
            from datetime import datetime
            return datetime.now().isoformat()
        return ''

    def _evaluate_arithmetic(self, expr, row, col):
        # A small, forgiving evaluator for arithmetic and string concatenation.
        expr = expr.strip()
        # Replace cell refs with values.
        def replace_cell(match):
            ref = match.group(0).upper()
            pos = cell_ref_to_rc(ref)
            if not pos:
                return '0'
            val = self.evaluate_cell(*pos)
            return self._literal(val)

        expr = re.sub(r'(?<![A-Z0-9_])[A-Z]+\d+(?![A-Z0-9_])', replace_cell, expr)
        expr = expr.replace('^', '**')

        # Replace range shorthand like A1:A3 with first value for simple arithmetic fallback.
        expr = re.sub(r'\b([A-Z]+\d+):([A-Z]+\d+)\b', lambda m: str(self._evaluate_arg(m.group(0), row, col)), expr)

        try:
            # Safe evaluation of a limited expression.
            allowed = {'__builtins__': {} }
            value = eval(expr, allowed, {})
            return value
        except Exception:
            return expr

    def _literal(self, value):
        if isinstance(value, str):
            if value.startswith('"') and value.endswith('"'):
                return value
            if self._is_number(value):
                return str(float(value))
            return repr(value)
        if isinstance(value, (int, float)):
            return str(value)
        return repr(str(value))

    def _truthy(self, value):
        if isinstance(value, list):
            return any(self._truthy(v) for v in value)
        if value in ('', None):
            return False
        if isinstance(value, str):
            return value.strip().lower() not in ('false', '0', 'no', 'n/a', 'na')
        return bool(value)

    @staticmethod
    def _is_number(value):
        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False


def flatten_list(values):
    out = []
    for value in values:
        if isinstance(value, list):
            out.extend(flatten_list(value))
        else:
            out.append(value)
    return out


def split_args(text):
    if not text.strip():
        return []
    args = []
    current = ''
    depth = 0
    in_quote = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            in_quote = not in_quote
            current += ch
        elif ch == '(' and not in_quote:
            depth += 1
            current += ch
        elif ch == ')' and not in_quote:
            depth -= 1
            current += ch
        elif ch == ',' and not in_quote and depth == 0:
            args.append(current.strip())
            current = ''
        else:
            current += ch
        i += 1
    if current.strip():
        args.append(current.strip())
    return args
