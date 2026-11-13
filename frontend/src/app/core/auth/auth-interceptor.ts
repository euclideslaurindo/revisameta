import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { TranslocoService } from '@jsverse/transloco';
import { catchError, from, switchMap, throwError } from 'rxjs';

import { AuthService, SKIP_REFRESH } from './auth';

const API_PREFIX = '/api/';

function withHeaders(request: HttpRequest<unknown>, token: string | null, language: string) {
  const headers: Record<string, string> = { 'Accept-Language': language };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return request.clone({ setHeaders: headers, withCredentials: true });
}

/**
 * Adds the bearer token and the interface language to API calls. On a 401 it tries one
 * silent refresh and repeats the request; if that fails, the session is over.
 */
export const authInterceptor: HttpInterceptorFn = (request, next) => {
  if (!request.url.startsWith(API_PREFIX)) {
    return next(request);
  }
  const auth = inject(AuthService);
  const language = inject(TranslocoService).getActiveLang();

  return next(withHeaders(request, auth.accessToken(), language)).pipe(
    catchError((error: unknown) => {
      const unauthorized = error instanceof HttpErrorResponse && error.status === 401;
      if (!unauthorized || request.context.get(SKIP_REFRESH)) {
        return throwError(() => error);
      }
      return from(auth.refresh()).pipe(
        switchMap((ok) => {
          if (!ok) {
            void auth.expire();
            return throwError(() => error);
          }
          return next(withHeaders(request, auth.accessToken(), language));
        }),
      );
    }),
  );
};
