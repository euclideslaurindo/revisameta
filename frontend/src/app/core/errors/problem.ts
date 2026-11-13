import { HttpErrorResponse } from '@angular/common/http';

export interface Problem {
  code: string;
  title: string;
  status: number;
}

/**
 * The backend answers errors as Problem Details already translated to the
 * language sent in Accept-Language. Returns null for network failures.
 */
export function asProblem(error: unknown): Problem | null {
  if (error instanceof HttpErrorResponse && error.error && typeof error.error === 'object') {
    const body = error.error as Partial<Problem>;
    if (typeof body.code === 'string' && typeof body.title === 'string') {
      return { code: body.code, title: body.title, status: error.status };
    }
  }
  return null;
}
