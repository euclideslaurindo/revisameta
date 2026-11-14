import {
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { TranslocoPipe } from '@jsverse/transloco';
import { NgxExtendedPdfViewerModule, PageRenderedEvent } from 'ngx-extended-pdf-viewer';

import { Api } from '../../core/api/api';
import { createAnnotation } from '../../core/api/fn/pdfs/create-annotation';
import { listAnnotations } from '../../core/api/fn/pdfs/list-annotations';
import { listPdfs } from '../../core/api/fn/pdfs/list-pdfs';
import { viewPdf } from '../../core/api/fn/pdfs/view-pdf';
import { getStudy } from '../../core/api/fn/studies/get-study';
import { AnnotationOut } from '../../core/api/models/annotation-out';
import { PdfOut } from '../../core/api/models/pdf-out';
import { PdfViewOut } from '../../core/api/models/pdf-view-out';
import { FormError } from '../../shared/form-error';
import { paintAll, paintPage } from './pdf-highlights';
import { readPdfSelection } from './pdf-selection';

/**
 * The PDFs of a study beside a form: choose the article, mark passages (painted on the
 * pages) and hand the list of passages to the form, so each answer can point to one.
 */
@Component({
  selector: 'rm-study-pdf-pane',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    NgxExtendedPdfViewerModule,
    FormError,
  ],
  template: `
    @if (loaded() && pdfs().length === 0) {
      <p class="empty">{{ 'extraction.noPdf' | transloco }}</p>
    }
    @if (pdfs().length > 1) {
      <mat-form-field subscriptSizing="dynamic">
        <mat-label>PDF</mat-label>
        <mat-select [ngModel]="pdf()?.id" (ngModelChange)="open($event)">
          @for (p of pdfs(); track p.id) {
            <mat-option [value]="p.id">{{ p.original_filename }}</mat-option>
          }
        </mat-select>
      </mat-form-field>
    }
    @if (pdf(); as p) {
      <ngx-extended-pdf-viewer
        [src]="p.url"
        [(page)]="page"
        [showOpenFileButton]="false"
        [showSecondaryToolbarButton]="false"
        [useInlineScripts]="false"
        height="70vh"
        (pageRendered)="onPageRendered($event)"
      />
      @if (canMark()) {
        <div class="actions">
          <button mat-stroked-button type="button" (click)="mark()">
            {{ 'pdfs.annotations.mark' | transloco }}
          </button>
        </div>
        @if (selectionMissing()) {
          <p class="notice notice-warn" role="status">
            {{ 'pdfs.annotations.selectFirst' | transloco }}
          </p>
        }
      }
    }
    <rm-form-error [error]="error()" />
  `,
})
export class StudyPdfPane {
  private readonly api = inject(Api);
  private readonly host = inject(ElementRef<HTMLElement>);

  readonly projectId = input.required<string>();
  readonly studyId = input.required<string>();
  readonly canMark = input(false);
  readonly annotationsChange = output<AnnotationOut[]>();

  protected readonly pdfs = signal<PdfOut[]>([]);
  protected readonly pdf = signal<PdfViewOut | null>(null);
  protected readonly loaded = signal(false);
  protected readonly selectionMissing = signal(false);
  protected readonly error = signal<unknown>(null);
  private readonly annotations = signal<AnnotationOut[]>([]);
  private readonly onPage = computed(() => {
    const id = this.pdf()?.id;
    return this.annotations().filter((a) => a.pdf_file_id === id);
  });
  protected page = 1;

  constructor() {
    effect(() => void this.load(this.studyId()));
    effect(() => paintAll(this.host.nativeElement, this.onPage()));
  }

  /** Jumps to a passage (used by the form's "see in the PDF"). */
  async show(annotation: AnnotationOut): Promise<void> {
    if (this.pdf()?.id !== annotation.pdf_file_id) await this.open(annotation.pdf_file_id);
    this.page = annotation.page;
  }

  protected onPageRendered(event: PageRenderedEvent): void {
    paintPage(this.host.nativeElement, event.pageNumber, this.onPage());
  }

  private async load(studyId: string): Promise<void> {
    const project_id = this.projectId();
    try {
      const study = await this.api.invoke(getStudy, { project_id, study_id: studyId });
      const lists = await Promise.all(
        study.reports.map((r) => this.api.invoke(listPdfs, { project_id, report_id: r.id })),
      );
      this.pdfs.set(lists.flat());
      await this.reload();
      if (this.pdfs().length) await this.open(this.pdfs()[0].id);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.loaded.set(true);
    }
  }

  protected async open(pdfId: string): Promise<void> {
    this.pdf.set(await this.api.invoke(viewPdf, { project_id: this.projectId(), pdf_id: pdfId }));
  }

  private async reload(): Promise<void> {
    const lists = await Promise.all(
      this.pdfs().map((p) =>
        this.api.invoke(listAnnotations, { project_id: this.projectId(), pdf_id: p.id }),
      ),
    );
    this.annotations.set(lists.flat());
    this.annotationsChange.emit(this.annotations());
  }

  async mark(): Promise<void> {
    const selection = readPdfSelection();
    this.selectionMissing.set(!selection);
    const pdf = this.pdf();
    if (!selection || !pdf) return;
    try {
      await this.api.invoke(createAnnotation, {
        project_id: this.projectId(),
        pdf_id: pdf.id,
        body: selection,
      });
      window.getSelection()?.removeAllRanges();
      await this.reload();
    } catch (error) {
      this.error.set(error);
    }
  }
}
