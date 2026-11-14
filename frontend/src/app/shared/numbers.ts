/**
 * Number entry accepts comma or dot as decimal separator (docs/modulos.md 10.3) and is
 * sent to the API as a plain decimal string; storage is always numeric.
 */
export function parseDecimal(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim().replace(/\s/g, '');
  if (!text) return null;
  // "1.234,5" (pt-BR thousands) -> "1234.5"; "1,5" -> "1.5"; "1.5" stays.
  const normalized = text.includes(',') ? text.replace(/\./g, '').replace(',', '.') : text;
  return /^-?\d+(\.\d+)?$/.test(normalized) ? normalized : null;
}

export function parseInteger(value: string | number | null | undefined): number | null {
  const decimal = parseDecimal(value);
  if (decimal === null || decimal.includes('.')) return null;
  return Number(decimal);
}

/** True when the text is empty or a valid number (used to flag typing mistakes early). */
export function isValidNumberText(value: string | null | undefined, integer = false): boolean {
  if (value === null || value === undefined || !String(value).trim()) return true;
  return integer ? parseInteger(value) !== null : parseDecimal(value) !== null;
}
