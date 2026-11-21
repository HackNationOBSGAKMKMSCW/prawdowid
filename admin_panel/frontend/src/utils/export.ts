/** Client-side export of what is on screen (CSV for spreadsheets, JSON for tools). */

function download(filename: string, content: string, type: string): void {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function stamp(): string {
  return new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-');
}

function cell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
  // Neutralise spreadsheet formulas (CSV injection) and quote every cell.
  const safe = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;
  return `"${safe.replace(/"/g, '""')}"`;
}

export function exportCsv<T>(name: string, rows: T[], columns: { header: string; value: (row: T) => unknown }[]): void {
  const lines = [columns.map((c) => cell(c.header)).join(';')];
  for (const row of rows) lines.push(columns.map((c) => cell(c.value(row))).join(';'));
  // BOM so Excel opens Polish characters correctly.
  download(`${name}-${stamp()}.csv`, `﻿${lines.join('\r\n')}`, 'text/csv;charset=utf-8');
}

export function exportJson(name: string, data: unknown): void {
  download(`${name}-${stamp()}.json`, JSON.stringify(data, null, 2), 'application/json');
}
