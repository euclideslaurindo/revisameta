/**
 * Reading the result in plain language (docs/modulos.md 7.7, step 5). No statistics
 * here: every number comes from the R service; these functions only decide which
 * sentence to show and format the numbers for the screen.
 */

export type Favoured = 'group1' | 'group2' | 'none';
export type Heterogeneity = 'low' | 'moderate' | 'substantial' | 'considerable';

/** Ratio measures are shown on their original scale (exp), the others as they are. */
export function isRatio(measure: string): boolean {
  return measure === 'OR' || measure === 'RR';
}

/**
 * Which group the result favours: only when the 95% CI excludes the null value
 * (0 on the analysis scale). `favoursRight` says which group a positive effect favours.
 */
export function favoured(ciLb: number, ciUb: number, favoursRight: 'group1' | 'group2'): Favoured {
  const left = favoursRight === 'group1' ? 'group2' : 'group1';
  if (ciLb > 0) return favoursRight;
  if (ciUb < 0) return left;
  return 'none';
}

/**
 * Plain-language reading of I², following the overlapping ranges of the Cochrane
 * Handbook (10.10.2): 0–40% might not be important, 30–60% moderate, 50–90%
 * substantial, 75–100% considerable. The cut points used here are 40, 60 and 75.
 */
export function heterogeneity(i2: number): Heterogeneity {
  if (i2 < 40) return 'low';
  if (i2 < 60) return 'moderate';
  if (i2 < 75) return 'substantial';
  return 'considerable';
}

/** A number for the screen with the decimal mark of the language. */
export function formatNumber(value: number | null | undefined, lang: string, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const text = value.toFixed(digits);
  return lang.startsWith('pt') ? text.replace('.', ',') : text;
}

/** An effect on the scale people read (exp for OR/RR). */
export function shown(value: number, measure: string): number {
  return isRatio(measure) ? Math.exp(value) : value;
}

export function formatP(p: number | null | undefined, lang: string): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return '—';
  if (p < 0.001) return lang.startsWith('pt') ? '< 0,001' : '< 0.001';
  return formatNumber(p, lang, 3);
}
