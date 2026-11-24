import { countWords } from './text-count';

describe('countWords', () => {
  it('counts words separated by any whitespace', () => {
    expect(countWords('')).toBe(0);
    expect(countWords('   ')).toBe(0);
    expect(countWords('Objetivo: avaliar  a cirurgia.\n\nMétodos: busca')).toBe(6);
  });
});
