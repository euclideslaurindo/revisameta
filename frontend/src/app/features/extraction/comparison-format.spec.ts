import { describe, expect, it } from 'vitest';

import { ItemOut } from '../../core/api/models/item-out';
import { fieldLabel, formatValue, placeLabel } from './comparison-format';

const t = (key: string, params?: Record<string, unknown>) =>
  params ? `${key}:${JSON.stringify(params)}` : key;

function item(over: Partial<ItemOut>): ItemOut {
  return {
    key: 'k',
    section: 'row',
    kind: 'number',
    field: 'sd',
    value_a: null,
    value_b: null,
    agree: false,
    divergent: true,
    ...over,
  };
}

describe('comparison display', () => {
  it('shows numbers with the separator of the language, without rounding', () => {
    expect(formatValue(item({}), '11.25', 'pt-BR', t)).toBe('11,25');
    expect(formatValue(item({}), '11.25', 'en', t)).toBe('11.25');
    expect(formatValue(item({}), null, 'pt-BR', t)).toBe('—');
  });

  it('translates codes instead of showing them', () => {
    expect(
      formatValue(item({ field: 'dispersion_type', kind: 'category' }), 'se', 'pt-BR', t),
    ).toBe('extraction.dispersion.se');
    expect(formatValue(item({ field: 'present', kind: 'category' }), false, 'pt-BR', t)).toBe(
      'consensus.value.absent',
    );
    expect(formatValue(item({ field: 'adjusted', kind: 'category' }), true, 'pt-BR', t)).toBe(
      'consensus.value.yes',
    );
  });

  it('formats an effect reported by the article', () => {
    const effect = { measure: 'OR', estimate: '1.5', ci_low: '1.1', ci_high: '2.05', se: null };
    expect(formatValue(item({ field: 'effect_reported' }), effect, 'pt-BR', t)).toBe(
      'OR 1,5 (1,1–2,05)',
    );
  });

  it('names fields and places', () => {
    expect(fieldLabel(item({}), t)).toBe('extraction.data.fields.sd');
    expect(
      fieldLabel(item({ section: 'characteristics', field: 'x', label: 'Anestesia' }), t),
    ).toBe('Anestesia');
    expect(
      placeLabel(
        item({ outcome_id: 'o1', timepoint: '5 anos', arm_label: 'Precoce' }),
        () => 'QI',
        t,
      ),
    ).toBe('consensus.section.row:{"outcome":"QI","timepoint":"5 anos","arm":"Precoce"}');
  });
});
