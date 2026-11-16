import { cellClass } from './rob-table-page';

describe('risk-of-bias table colours', () => {
  it('colours answers and stars like the judgements they suggest', () => {
    expect(cellClass('Y')).toContain('rob-level-low');
    expect(cellClass('N')).toContain('rob-level-high');
    expect(cellClass('stars_2_of_2')).toContain('rob-level-low');
    expect(cellClass('stars_1_of_2')).toContain('rob-level-moderate');
    expect(cellClass('stars_0_of_1')).toContain('rob-level-high');
    expect(cellClass('serious')).toContain('rob-level-serious');
    expect(cellClass(null)).toContain('rob-level-empty');
  });
});
