import { Calibration, toData } from './digitizer-math';

const base: Calibration = {
  x1: { x: 100, y: 500 },
  x2: { x: 500, y: 500 },
  y1: { x: 100, y: 500 },
  y2: { x: 100, y: 100 },
  vx1: 0,
  vx2: 10,
  vy1: 0,
  vy2: 100,
  logX: false,
  logY: false,
};

describe('digitizer geometry', () => {
  it('maps pixels linearly between the calibration points (y grows downwards)', () => {
    const p = toData({ x: 300, y: 300 }, base);
    expect(p.x).toBeCloseTo(5);
    expect(p.y).toBeCloseTo(50);
  });

  it('works on a log axis', () => {
    const p = toData({ x: 300, y: 300 }, { ...base, vy1: 1, vy2: 100, logY: true });
    expect(p.y).toBeCloseTo(10);
  });

  it('extrapolates outside the calibration points', () => {
    expect(toData({ x: 700, y: 500 }, base).x).toBeCloseTo(15);
  });
});
