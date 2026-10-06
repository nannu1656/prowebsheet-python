const state = {
  rows: 50,
  cols: 20,
  cells: {},
  selected: { row: 0, col: 0 },
};

const colHeaders = document.getElementById('col-headers');
const rowHeaders = document.getElementById('row-headers');
const grid = document.getElementById('grid');
const formulaInput = document.getElementById('formula-input');
const cellAddress = document.getElementById('cell-address');
const fileInput = document.getElementById('file-input');

function colLabel(index) {
  let label = '';
  let n = index + 1;
  while (n > 0) {
    n -= 1;
    label = String.fromCharCode(65 + (n % 26)) + label;
    n = Math.floor(n / 26);
  }
  return label;
}

async function fetchSheet() {
  const res = await fetch('/api/sheet');
  const data = await res.json();
  state.rows = data.rows || 50;
  state.cols = data.cols || 20;
  state.cells = data.cells || {};
  render();
}

function renderHeaders() {
  colHeaders.innerHTML = '';
  for (let c = 0; c < state.cols; c++) {
    const el = document.createElement('div');
    el.className = 'col-header';
    el.textContent = colLabel(c);
    colHeaders.appendChild(el);
  }

  rowHeaders.innerHTML = '';
  for (let r = 0; r < state.rows; r++) {
    const el = document.createElement('div');
    el.className = 'row-header';
    el.textContent = String(r + 1);
    rowHeaders.appendChild(el);
  }
}

function renderGrid() {
  grid.innerHTML = '';
  const inner = document.createElement('div');
  inner.className = 'grid-inner';
  inner.style.gridTemplateColumns = `repeat(${state.cols}, 100px)`;

  for (let r = 0; r < state.rows; r++) {
    for (let c = 0; c < state.cols; c++) {
      const key = `${r}:${c}`;
      const cell = document.createElement('div');
      cell.className = 'cell';
      cell.dataset.row = r;
      cell.dataset.col = c;
      cell.dataset.key = key;
      cell.textContent = getDisplayValue(r, c);
      if (state.selected.row === r && state.selected.col === c) {
        cell.classList.add('selected');
      }
      cell.addEventListener('click', () => selectCell(r, c));
      inner.appendChild(cell);
    }
  }

  grid.appendChild(inner);
}

function getDisplayValue(r, c) {
  const value = state.cells[`${r}:${c}`] || '';
  if (!value.startsWith('=')) return value;
  return evaluateFormula(value, r, c);
}

function evaluateFormula(formula, row, col) {
  const text = formula.slice(1).trim();
  const matches = text.match(/^([A-Z_]+)\s*\((.*)\)$/i);
  if (matches) {
    const fn = matches[1].toUpperCase();
    const rawArgs = matches[2];
    const args = splitArgs(rawArgs);
    const values = args.map((a) => evalArg(a, row, col));
    if (fn === 'SUM') return values.flat().filter(v => !isNaN(Number(v))).reduce((a, b) => a + Number(b), 0);
    if (fn === 'AVERAGE') {
      const arr = values.flat().filter(v => !isNaN(Number(v)));
      return arr.length ? arr.reduce((a, b) => a + Number(b), 0) / arr.length : 0;
    }
    if (fn === 'MIN') {
      const arr = values.flat().filter(v => !isNaN(Number(v)));
      return arr.length ? Math.min(...arr.map(Number)) : 0;
    }
    if (fn === 'MAX') {
      const arr = values.flat().filter(v => !isNaN(Number(v)));
      return arr.length ? Math.max(...arr.map(Number)) : 0;
    }
    if (fn === 'COUNT') {
      return values.flat().filter(v => !isNaN(Number(v))).length;
    }
  }

  const replaced = text.replace(/[A-Z]+\d+/g, ref => {
    const pos = cellToRC(ref);
    if (!pos) return '0';
    const cellVal = state.cells[`${pos.row}:${pos.col}`] || '';
    if (cellVal.startsWith('=')) return evaluateFormula(cellVal, pos.row, pos.col);
    return Number(cellVal) || 0;
  });

  try {
    return Function(`"use strict"; return (${replaced})`)();
  } catch {
    return '#ERROR';
  }
}

function evalArg(arg, row, col) {
  const text = arg.trim();
  if (!text) return '';
  if (text.includes(':')) {
    const [a, b] = text.split(':');
    const aPos = cellToRC(a);
    const bPos = cellToRC(b);
    if (!aPos || !bPos) return [];
    const vals = [];
    for (let r = Math.min(aPos.row, bPos.row); r <= Math.max(aPos.row, bPos.row); r++) {
      for (let c = Math.min(aPos.col, bPos.col); c <= Math.max(aPos.col, bPos.col); c++) {
        const raw = state.cells[`${r}:${c}`] || '';
        vals.push(raw.startsWith('=') ? evaluateFormula(raw, r, c) : Number(raw) || raw);
      }
    }
    return vals;
  }
  if (/[A-Z]+\d+/i.test(text)) {
    const pos = cellToRC(text);
    if (!pos) return text;
    const raw = state.cells[`${pos.row}:${pos.col}`] || '';
    return raw.startsWith('=') ? evaluateFormula(raw, pos.row, pos.col) : raw;
  }
  return Number(text) || text;
}

function splitArgs(text) {
  const args = [];
  let current = '';
  let depth = 0;
  let inQuote = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') inQuote = !inQuote;
    if (ch === '(' && !inQuote) depth++;
    if (ch === ')' && !inQuote) depth--;
    if (ch === ',' && !inQuote && depth === 0) {
      args.push(current.trim());
      current = '';
      continue;
    }
    current += ch;
  }
  if (current.trim()) args.push(current.trim());
  return args;
}

function cellToRC(ref) {
  const match = ref.match(/^([A-Z]+)(\d+)$/i);
  if (!match) return null;
  const col = match[1].toUpperCase();
  let index = 0;
  for (let i = 0; i < col.length; i++) index = index * 26 + (col.charCodeAt(i) - 64);
  const row = Number(match[2]) - 1;
  return { row, col: index - 1 };
}

function selectCell(row, col) {
  state.selected = { row, col };
  cellAddress.value = `${colLabel(col)}${row + 1}`;
  formulaInput.value = state.cells[`${row}:${col}`] || '';
  renderGrid();
}

function updateCellFromInput() {
  const { row, col } = state.selected;
  const value = formulaInput.value.trim();
  fetch('/api/cell', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ row, col, value }),
  }).then(() => fetchSheet());
}

formulaInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    updateCellFromInput();
  }
});

formulaInput.addEventListener('blur', updateCellFromInput);

async function resetSheet() {
  await fetch('/api/sheet', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows: 50, cols: 20, cells: {}, styles: {} }),
  });
  await fetchSheet();
}

document.getElementById('new-sheet').addEventListener('click', resetSheet);

document.getElementById('export-csv').addEventListener('click', () => window.location.href = '/api/export/csv');
document.getElementById('export-xlsx').addEventListener('click', () => window.location.href = '/api/export/xlsx');

document.getElementById('load-csv').addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  await fetch('/api/import/csv', { method: 'POST', body: formData });
  await fetchSheet();
  fileInput.value = '';
});

function render() {
  renderHeaders();
  renderGrid();
  const { row, col } = state.selected;
  cellAddress.value = `${colLabel(col)}${row + 1}`;
  formulaInput.value = state.cells[`${row}:${col}`] || '';
}

fetchSheet();
