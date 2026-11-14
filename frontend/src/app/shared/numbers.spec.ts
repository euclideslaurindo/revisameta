import { describe, expect, it } from 'vitest';

import {
  displayDecimal,
  displayParams,
  isValidNumberText,
  parseDecimal,
  parseInteger,
} from './numbers';

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

describe('number display', () => {
  it('uses the separator of the language without rounding', () => {
    expect(displayDecimal('92.5', 'pt-BR')).toBe('92,5');
    expect(displayDecimal('92.5', 'en')).toBe('92.5');
    expect(displayDecimal('0.123456789', 'pt-BR')).toBe('0,123456789');
    expect(displayDecimal(30, 'pt-BR')).toBe('30');
    expect(displayDecimal(null, 'pt-BR')).toBe('');
  });

  it('leaves text that is not a number untouched', () => {
    expect(displayDecimal('12 meses', 'pt-BR')).toBe('12 meses');
    expect(
      displayParams({ value: '170', min: '40.5', outcome: 'Escore 1.0 beta' }, 'pt-BR'),
    ).toEqual({
      value: '170',
      min: '40,5',
      outcome: 'Escore 1.0 beta',
    });
  });
});
