import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Api } from '../api/api';
import { JobOut } from '../api/models/job-out';
import { AuthService } from '../auth/auth';
import { JobProgressService } from './job-progress';

function job(status: string, progress: number): JobOut {
  return {
    id: 'job-1',
    kind: 'process_upload',
    status,
    progress,
    result: null,
    error_code: null,
    updated_at: '2026-11-14T00:00:00Z',
  };
}

function sseResponse(events: JobOut[]): Response {
  const body = events.map((e) => `event: progress\ndata: ${JSON.stringify(e)}\n\n`).join('');
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

describe('JobProgressService (ADR-005)', () => {
  const invoke = vi.fn();
  let service: JobProgressService;

  beforeEach(() => {
    invoke.mockReset();
    TestBed.configureTestingModule({
      providers: [
        { provide: Api, useValue: { invoke } },
        { provide: AuthService, useValue: { accessToken: () => 'token' } },
      ],
    });
    service = TestBed.inject(JobProgressService);
  });

  afterEach(() => vi.unstubAllGlobals());

  it('follows the SSE stream and sends the bearer token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([job('running', 40), job('succeeded', 100)]));
    vi.stubGlobal('fetch', fetchMock);
    const seen: number[] = [];
    const final = await service.follow('p1', 'job-1', (j) => seen.push(j.progress));
    expect(final.status).toBe('succeeded');
    expect(seen).toEqual([40, 100]);
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer token');
    expect(invoke).not.toHaveBeenCalled();
  });

  it('falls back to polling when SSE is unavailable', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('stream not supported')));
    invoke.mockResolvedValueOnce(job('running', 10)).mockResolvedValueOnce(job('succeeded', 100));
    const seen: string[] = [];
    const promise = service.follow('p1', 'job-1', (j) => seen.push(j.status));
    await vi.runAllTimersAsync();
    const final = await promise;
    vi.useRealTimers();
    expect(final.status).toBe('succeeded');
    expect(seen).toEqual(['running', 'succeeded']);
    expect(invoke).toHaveBeenCalledTimes(2);
  });

  it('falls back to polling when the stream ends before a final state', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([job('running', 50)])));
    invoke.mockResolvedValueOnce(job('failed', 50));
    const promise = service.follow('p1', 'job-1', () => undefined);
    await vi.runAllTimersAsync();
    expect((await promise).status).toBe('failed');
    vi.useRealTimers();
  });
});
