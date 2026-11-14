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

/**
 * File downloads ask for a Blob, so their error bodies arrive as a Blob too. This
 * turns such an error back into a regular Problem Details error.
 */
export async function withJsonBody(error: unknown): Promise<unknown> {
  if (error instanceof HttpErrorResponse && error.error instanceof Blob) {
    try {
      const body: unknown = JSON.parse(await error.error.text());
      return new HttpErrorResponse({
        error: body,
        headers: error.headers,
        status: error.status,
        statusText: error.statusText,
        url: error.url ?? undefined,
      });
    } catch {
      return error;
    }
  }
  return error;
}
