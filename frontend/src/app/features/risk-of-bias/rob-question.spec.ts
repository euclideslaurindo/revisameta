import { MISSING } from './rob-question';

describe('MISSING (hint to answer "No information")', () => {
  it('recognises justifications saying the article does not report something', () => {
    for (const text of [
      'O artigo não informa como os grupos foram formados',
      'nao relata perdas de seguimento',
      'The paper does not report blinding',
      'no information on confounders',
      'não está claro no texto',
    ]) {
      expect(MISSING.test(text.toLowerCase())).toBe(true);
    }
  });

  it('ignores justifications that describe an actual problem', () => {
    for (const text of [
      'Os grupos diferem em idade e não houve ajuste',
      'Perda de 40% no grupo tardio',
      'Outcome assessors knew the group',
    ]) {
      expect(MISSING.test(text.toLowerCase())).toBe(false);
    }
  });
});
