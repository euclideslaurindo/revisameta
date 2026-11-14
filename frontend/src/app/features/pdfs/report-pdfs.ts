import { Component, OnInit, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { attachPdf } from '../../core/api/fn/pdfs/attach-pdf';
import { listPdfs } from '../../core/api/fn/pdfs/list-pdfs';
import { PdfOut } from '../../core/api/models/pdf-out';
import { PdfUploadService, UploadProgress } from '../../core/uploads/pdf-upload';
import { FormError } from '../../shared/form-error';

/** PDFs of one article: list, open, and upload with resume after a dropped connection. */
@Component({
  selector: 'rm-report-pdfs',
  imports: [RouterLink, TranslocoPipe, MatButtonModule, MatProgressBarModule, FormError],
  template: `
    <div class="pdf-box">
      @for (pdf of pdfs(); track pdf.id) {
        <div class="pdf-row">
          <a [routerLink]="['/projetos', projectId(), 'pdfs', pdf.id]">{{
            pdf.original_filename
          }}</a>
          <span class="muted">
            @if (pdf.page_count) {
              {{ 'pdfs.pages' | transloco: { count: pdf.page_count } }} ·
            }
            {{ 'pdfs.textStatus.' + pdf.text_status | transloco }}
          </span>
        </div>
      }
      @if (canUpload()) {
        @if (progress(); as p) {
          <p role="status">{{ 'pdfs.phase.' + p.phase | transloco }} {{ p.percent }}%</p>
          <mat-progress-bar mode="determinate" [value]="p.percent" />
        }
        <rm-form-error [error]="error()" />
        @if (failure(); as key) {
          <div class="notice notice-error" role="alert">{{ key | transloco }}</div>
        }
        @if (pendingFile() && !busy()) {
          <button mat-stroked-button type="button" (click)="resume()">
            {{ 'pdfs.resume' | transloco }}
          </button>
        }
        <label class="file-input">
          <span>{{ 'pdfs.attach' | transloco }}</span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            [disabled]="busy()"
            (change)="choose($event)"
          />
        </label>
      }
    </div>
  `,
})
export class ReportPdfs implements OnInit {
  private readonly api = inject(Api);
  private readonly uploads = inject(PdfUploadService);

  readonly projectId = input.required<string>();
  readonly reportId = input.required<string>();
  readonly canUpload = input(false);

  protected readonly pdfs = signal<PdfOut[]>([]);
  protected readonly progress = signal<UploadProgress | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly pendingFile = signal<File | null>(null);
  protected readonly failure = signal<string | null>(null);
  private pendingUploadId: string | undefined;

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  private async reload(): Promise<void> {
    this.pdfs.set(
      await this.api.invoke(listPdfs, { project_id: this.projectId(), report_id: this.reportId() }),
    );
  }

  async choose(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    this.pendingUploadId = undefined;
    await this.send(file);
  }

  resume(): Promise<void> {
    const file = this.pendingFile();
    return file ? this.send(file) : Promise.resolve();
  }

  private async send(file: File): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    this.failure.set(null);
    this.pendingFile.set(file);
    try {
      const { uploadId, job } = await this.uploads.upload(
        this.projectId(),
        file,
        (p) => this.progress.set(p),
        this.pendingUploadId,
        (id) => (this.pendingUploadId = id),
      );
      this.pendingUploadId = uploadId;
      if (job.status !== 'succeeded') {
        // Processing failed (e.g. not a real PDF): start over with another file.
        this.failure.set(
          job.error_code === 'upload.not_pdf' ? 'pdfs.errors.notPdf' : 'pdfs.errors.failed',
        );
        this.pendingFile.set(null);
        this.pendingUploadId = undefined;
        this.progress.set(null);
        return;
      }
      await this.api.invoke(attachPdf, {
        project_id: this.projectId(),
        report_id: this.reportId(),
        body: { upload_id: uploadId },
      });
      this.pendingFile.set(null);
      this.pendingUploadId = undefined;
      this.progress.set(null);
      await this.reload();
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
