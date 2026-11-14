import { HttpErrorResponse } from '@angular/common/http';
import { describe, expect, it } from 'vitest';

import { asProblem, withJsonBody } from '../core/errors/problem';
import { fileNameFrom } from './download';

describe('downloads', () => {
  it('reads the file name sent by the server', () => {
    const header = `attachment; filename="projeto_extracao_2026-11-14.xlsx"; filename*=UTF-8''projeto_extra%C3%A7%C3%A3o.xlsx`;
    expect(fileNameFrom(header, 'x')).toBe('projeto_extração.xlsx');
    expect(fileNameFrom('attachment; filename="a.csv"', 'x')).toBe('a.csv');
    expect(fileNameFrom(null, 'x')).toBe('x');
  });

  it('turns an error that came as a Blob back into a Problem', async () => {
    const body = { code: 'export.incomplete', title: '1 estudo ficaria fora', status: 409 };
    const error = new HttpErrorResponse({
      error: new Blob([JSON.stringify(body)], { type: 'application/problem+json' }),
      status: 409,
    });
    expect(asProblem(error)).toBeNull();
    expect(asProblem(await withJsonBody(error))?.code).toBe('export.incomplete');
  });
});
