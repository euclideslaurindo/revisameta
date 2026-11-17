import { favoured, formatNumber, formatP, heterogeneity, isRatio, shown } from './meta-reading';

describe('reading the meta-analysis result', () => {
  it('favours a group only when the 95% CI excludes the null', () => {
    expect(favoured(0.1, 0.9, 'group1')).toBe('group1');
    expect(favoured(-0.9, -0.1, 'group1')).toBe('group2');
    expect(favoured(-0.2, 0.4, 'group1')).toBe('none');
    // Undesirable event: a negative log RR favours group 1.
    expect(favoured(-0.9, -0.1, 'group2')).toBe('group1');
  });

  it('reads I² with the Cochrane Handbook ranges', () => {
    expect(heterogeneity(10)).toBe('low');
    expect(heterogeneity(45)).toBe('moderate');
    expect(heterogeneity(68)).toBe('substantial');
    expect(heterogeneity(92)).toBe('considerable');
  });

  it('shows ratio measures on their original scale and uses the decimal comma in Portuguese', () => {
    expect(isRatio('RR')).toBe(true);
    expect(isRatio('SMD')).toBe(false);
    expect(shown(0, 'RR')).toBe(1);
    expect(shown(-0.5, 'MD')).toBe(-0.5);
    expect(formatNumber(1.234, 'pt-BR')).toBe('1,23');
    expect(formatNumber(1.234, 'en')).toBe('1.23');
    expect(formatNumber(null, 'pt-BR')).toBe('—');
    expect(formatP(0.0001, 'pt-BR')).toBe('< 0,001');
    expect(formatP(0.0421, 'en')).toBe('0.042');
  });
});
