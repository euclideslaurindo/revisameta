import { describe, expect, it } from 'vitest';

import { isValidNumberText, parseDecimal, parseInteger } from './numbers';

describe('number entry (comma or dot)', () => {
  it('accepts both decimal separators', () => {
    expect(parseDecimal('11,2')).toBe('11.2');
    expect(parseDecimal('11.2')).toBe('11.2');
    expect(parseDecimal(' 1.234,5 ')).toBe('1234.5');
    expect(parseDecimal('-0,5')).toBe('-0.5');
  });

  it('rejects text that is not a number', () => {
    expect(parseDecimal('onze')).toBeNull();
    expect(parseDecimal('1,2,3')).toBeNull();
    expect(parseDecimal('')).toBeNull();
    expect(isValidNumberText('12a')).toBe(false);
    expect(isValidNumberText('')).toBe(true);
  });

  it('integers have no decimals', () => {
    expect(parseInteger('30')).toBe(30);
    expect(parseInteger('30,5')).toBeNull();
    expect(isValidNumberText('30,5', true)).toBe(false);
  });
});
