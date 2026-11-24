/**
 * Pixel -> axis value for the graph digitizer. Plain geometry (a linear map between two
 * calibration points per axis, or between their logarithms on a log axis); no
 * statistics. Image y grows downwards, which the two y calibration points absorb.
 */
export interface Point {
  x: number;
  y: number;
}

export interface Calibration {
  x1: Point;
  x2: Point;
  y1: Point;
  y2: Point;
  vx1: number;
  vx2: number;
  vy1: number;
  vy2: number;
  logX: boolean;
  logY: boolean;
}

function axis(pixel: number, p1: number, p2: number, v1: number, v2: number, log: boolean): number {
  const a = log ? Math.log10(v1) : v1;
  const b = log ? Math.log10(v2) : v2;
  const t = (pixel - p1) / (p2 - p1);
  const value = a + t * (b - a);
  return log ? 10 ** value : value;
}

export function toData(p: Point, c: Calibration): Point {
  return {
    x: axis(p.x, c.x1.x, c.x2.x, c.vx1, c.vx2, c.logX),
    y: axis(p.y, c.y1.y, c.y2.y, c.vy1, c.vy2, c.logY),
  };
}
