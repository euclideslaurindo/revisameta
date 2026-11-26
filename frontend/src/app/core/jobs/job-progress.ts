import { Injectable, inject } from '@angular/core';

import { Api } from '../api/api';
import { getJob } from '../api/fn/jobs/get-job';
import { JobOut } from '../api/models/job-out';
import { AuthService } from '../auth/auth';

const TERMINAL = new Set(['succeeded', 'failed']);
const POLL_MS = 1500;
const MAX_WAIT_MS = 15 * 60 * 1000;

/**
 * Follows a background job (ADR-005): SSE first, polling as fallback.
 *
 * Native EventSource cannot send the Authorization header, so the SSE stream is read
 * with fetch. When streaming is not available (e.g. the quick Cloudflare tunnel), the
 * service falls back to polling GET /jobs/{id} through the generated client.
 */
@Injectable({ providedIn: 'root' })
export class JobProgressService {
  private readonly api = inject(Api);
  private readonly auth = inject(AuthService);

  async follow(projectId: string, jobId: string, onUpdate: (job: JobOut) => void): Promise<JobOut> {
    try {
      const final = await this.stream(projectId, jobId, onUpdate);
      if (final) return final;
    } catch {
      // Fall through to polling.
    }
    return this.poll(projectId, jobId, onUpdate);
  }

  private async stream(
    projectId: string,
    jobId: string,
    onUpdate: (job: JobOut) => void,
  ): Promise<JobOut | null> {
    const token = this.auth.accessToken();
    const response = await fetch(`/api/v1/projects/${projectId}/jobs/${jobId}/events`, {
      headers: {
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    if (!response.ok || !response.body) return null;
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = '';
    let last: JobOut | null = null;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      const events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop() ?? '';
      for (const event of events) {
        const data = event
          .split(/\r?\n/)
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trim())
          .join('');
        if (!data) continue;
        const job = JSON.parse(data) as JobOut;
        if (!job.status) continue;
        last = job;
        onUpdate(job);
        if (TERMINAL.has(job.status)) return job;
      }
    }
    return last && TERMINAL.has(last.status) ? last : null;
  }

  private async poll(
    projectId: string,
    jobId: string,
    onUpdate: (job: JobOut) => void,
  ): Promise<JobOut> {
    const started = Date.now();
    for (;;) {
      const job = await this.api.invoke(getJob, { project_id: projectId, job_id: jobId });
      onUpdate(job);
      if (TERMINAL.has(job.status) || Date.now() - started > MAX_WAIT_MS) return job;
      await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    }
  }
}
