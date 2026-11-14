import { Injectable, inject } from '@angular/core';

import { Api } from '../api/api';
import { completeUpload } from '../api/fn/uploads/complete-upload';
import { createUpload } from '../api/fn/uploads/create-upload';
import { getUpload } from '../api/fn/uploads/get-upload';
import { partUrls } from '../api/fn/uploads/part-urls';
import { JobOut } from '../api/models/job-out';
import { JobProgressService } from '../jobs/job-progress';

export interface UploadProgress {
  phase: 'sending' | 'processing';
  percent: number;
}

const URL_BATCH = 10;
const PUT_RETRIES = 3;

/**
 * Sends a PDF straight to storage in parts (ADR-004). The parts go to signed URLs, not
 * to the API. If the connection drops, calling `upload` again with the same `uploadId`
 * sends only the parts the storage does not have yet.
 */
@Injectable({ providedIn: 'root' })
export class PdfUploadService {
  private readonly api = inject(Api);
  private readonly jobs = inject(JobProgressService);

  async upload(
    projectId: string,
    file: File,
    onProgress: (progress: UploadProgress) => void,
    uploadId?: string,
    onCreated?: (uploadId: string) => void,
  ): Promise<{ uploadId: string; job: JobOut }> {
    const upload = uploadId
      ? await this.api.invoke(getUpload, { project_id: projectId, upload_id: uploadId })
      : await this.api.invoke(createUpload, {
          project_id: projectId,
          body: { filename: file.name, size_bytes: file.size, content_type: 'application/pdf' },
        });
    onCreated?.(upload.id);
    const state = await this.api.invoke(getUpload, { project_id: projectId, upload_id: upload.id });
    const done = new Set(state.uploaded_parts ?? []);
    const missing = Array.from({ length: upload.part_count }, (_, i) => i + 1).filter((n) => !done.has(n));
    const report = () =>
      onProgress({ phase: 'sending', percent: Math.round((100 * done.size) / upload.part_count) });
    report();

    for (let start = 0; start < missing.length; start += URL_BATCH) {
      const batch = missing.slice(start, start + URL_BATCH);
      const urls = await this.api.invoke(partUrls, {
        project_id: projectId,
        upload_id: upload.id,
        body: { part_numbers: batch },
      });
      for (const { part_number, url } of urls) {
        const begin = (part_number - 1) * upload.part_size;
        await this.put(url, file.slice(begin, begin + upload.part_size));
        done.add(part_number);
        report();
      }
    }

    const job = await this.api.invoke(completeUpload, { project_id: projectId, upload_id: upload.id });
    const finished = await this.jobs.follow(projectId, job.id, (current) =>
      onProgress({ phase: 'processing', percent: current.progress }),
    );
    return { uploadId: upload.id, job: finished };
  }

  private async put(url: string, body: Blob): Promise<void> {
    let lastError: unknown;
    for (let attempt = 0; attempt < PUT_RETRIES; attempt++) {
      try {
        const response = await fetch(url, { method: 'PUT', body });
        if (response.ok) return;
        lastError = new Error(`upload part failed: ${response.status}`);
      } catch (error) {
        lastError = error;
      }
      await new Promise((resolve) => setTimeout(resolve, 500 * 2 ** attempt));
    }
    throw lastError;
  }
}
