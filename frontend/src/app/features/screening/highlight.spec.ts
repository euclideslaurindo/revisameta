import { highlight } from './highlight';

describe('highlight', () => {
  it('marks keywords ignoring case and accents', () => {
    const out = highlight('Coorte de Crianças operadas', ['criancas'], ['coorte']);
    expect(out).toEqual([
      { text: 'Coorte', kind: 'exclude' },
      { text: ' de ', kind: null },
      { text: 'Crianças', kind: 'include' },
      { text: ' operadas', kind: null },
    ]);
  });

  it('lets the longer keyword win when they overlap and ignores empty ones', () => {
    const out = highlight('rat model', [' ', 'rat model'], ['rat']);
    expect(out).toEqual([{ text: 'rat model', kind: 'include' }]);
    expect(highlight('', ['x'], [])).toEqual([]);
  });
});
