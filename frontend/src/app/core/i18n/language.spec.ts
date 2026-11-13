import { describe, expect, it } from 'vitest';

import { detectLanguage } from './language';

describe('detectLanguage', () => {
  it('prefers the saved choice', () => {
    expect(detectLanguage('en', ['pt-BR'])).toBe('en');
  });

  it('falls back to the browser languages, then pt-BR', () => {
    expect(detectLanguage(null, ['fr-FR', 'en-US'])).toBe('en');
    expect(detectLanguage(null, ['pt-PT'])).toBe('pt-BR');
    expect(detectLanguage('xx', ['de'])).toBe('pt-BR');
  });
});
