import { HttpErrorResponse } from '@angular/common/http';
import { describe, expect, it } from 'vitest';

import { asProblem } from './problem';

describe('asProblem', () => {
  it('reads Problem Details from the backend', () => {
    const error = new HttpErrorResponse({
      status: 409,
      error: {
        code: 'auth.email_taken',
        title: 'Já existe uma conta com este e-mail.',
        status: 409,
      },
    });
    expect(asProblem(error)).toEqual({
      code: 'auth.email_taken',
      title: 'Já existe uma conta com este e-mail.',
      status: 409,
    });
  });

  it('returns null for network errors', () => {
    expect(
      asProblem(new HttpErrorResponse({ status: 0, error: new ProgressEvent('error') })),
    ).toBeNull();
    expect(asProblem(new Error('x'))).toBeNull();
  });
});
