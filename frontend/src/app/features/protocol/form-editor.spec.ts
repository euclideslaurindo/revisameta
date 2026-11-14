import { describe, expect, it } from 'vitest';

import { keyFor } from './form-editor';

describe('form field keys', () => {
  it('turns a label into a snake_case key the backend accepts', () => {
    expect(keyFor('Tipo de anestesia', new Set())).toBe('tipo_de_anestesia');
    expect(keyFor('Idade média (anos)', new Set())).toBe('idade_media_anos');
    expect(keyFor('5 anos ou mais', new Set())).toBe('campo_5_anos_ou_mais');
    expect(keyFor('???', new Set())).toBe('campo');
  });

  it('never repeats a key', () => {
    expect(keyFor('País', new Set(['pais']))).toBe('pais_2');
    expect(keyFor('País', new Set(['pais', 'pais_2']))).toBe('pais_3');
  });

  it('respects the backend limit of 41 characters', () => {
    const key = keyFor('x'.repeat(80), new Set());
    expect(/^[a-z][a-z0-9_]{0,40}$/.test(key)).toBe(true);
  });
});
