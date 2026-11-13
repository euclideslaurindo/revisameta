import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthService } from './auth';
import { authInterceptor } from './auth-interceptor';

describe('authInterceptor', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  const auth = {
    token: 'old-token' as string | null,
    accessToken: () => auth.token,
    refresh: vi.fn(async () => {
      auth.token = 'new-token';
      return true;
    }),
    expire: vi.fn(async () => undefined),
  };

  beforeEach(() => {
    auth.token = 'old-token';
    auth.refresh.mockClear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: auth },
        { provide: TranslocoService, useValue: { getActiveLang: () => 'en' } },
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
  });

  it('sends the token, the language and the cookie only to the API', () => {
    http.get('/api/v1/projects').subscribe();
    const request = backend.expectOne('/api/v1/projects');
    expect(request.request.headers.get('Authorization')).toBe('Bearer old-token');
    expect(request.request.headers.get('Accept-Language')).toBe('en');
    expect(request.request.withCredentials).toBe(true);
    request.flush([]);

    http.get('/i18n/en.json').subscribe();
    const asset = backend.expectOne('/i18n/en.json');
    expect(asset.request.headers.has('Authorization')).toBe(false);
    asset.flush({});
  });

  it('refreshes once on 401 and repeats the request with the new token', async () => {
    let result: unknown;
    http.get('/api/v1/projects').subscribe((body) => (result = body));
    backend.expectOne('/api/v1/projects').flush({}, { status: 401, statusText: 'Unauthorized' });
    await Promise.resolve();
    await Promise.resolve();
    const retry = backend.expectOne('/api/v1/projects');
    expect(retry.request.headers.get('Authorization')).toBe('Bearer new-token');
    retry.flush(['ok']);
    expect(result).toEqual(['ok']);
    expect(auth.refresh).toHaveBeenCalledTimes(1);
  });

  it('ends the session when the refresh fails', async () => {
    auth.refresh.mockResolvedValueOnce(false);
    let failed = false;
    http.get('/api/v1/projects').subscribe({ error: () => (failed = true) });
    backend.expectOne('/api/v1/projects').flush({}, { status: 401, statusText: 'Unauthorized' });
    await Promise.resolve();
    await Promise.resolve();
    expect(failed).toBe(true);
    expect(auth.expire).toHaveBeenCalled();
  });
});
