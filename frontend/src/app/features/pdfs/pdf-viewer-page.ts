import { Component, ElementRef, computed, effect, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';
import {
  NgxExtendedPdfViewerModule,
  NgxExtendedPdfViewerService,
  PageRenderedEvent,
  pdfDefaultOptions,
} from 'ngx-extended-pdf-viewer';

import { paintAll, paintPage } from './pdf-highlights';

import { Api } from '../../core/api/api';
import { createAnnotation } from '../../core/api/fn/pdfs/create-annotation';
import { deleteAnnotation } from '../../core/api/fn/pdfs/delete-annotation';
import { listAnnotations } from '../../core/api/fn/pdfs/list-annotations';
import { searchPdf } from '../../core/api/fn/pdfs/search-pdf';
import { viewPdf } from '../../core/api/fn/pdfs/view-pdf';
import { AnnotationOut } from '../../core/api/models/annotation-out';
import { PdfViewOut } from '../../core/api/models/pdf-view-out';
import { SearchHit } from '../../core/api/models/search-hit';
import { AuthService } from '../../core/auth/auth';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { readPdfSelection } from './pdf-selection';

// Security (docs/riscos.md 10.1): never run JavaScript embedded in PDFs, and keep the
// viewer compatible with our CSP (no WebAssembly; pdf.js no longer uses eval).
pdfDefaultOptions.enableScripting = false;
pdfDefaultOptions.useWasm = false;

import { AiLocatePanel } from './ai-locate-panel';

@Component({
  selector: 'rm-pdf-viewer-page',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatTooltipModule,
    NgxExtendedPdfViewerModule,
    FormError,
    AiLocatePanel,
  ],
  template: `
    <rm-form-error [error]="error()" />
    @if (pdf(); as p) {
      <header class="page-header">
        <h2>{{ p.original_filename }}</h2>
        <span class="muted">{{ 'pdfs.textStatus.' + p.text_status | transloco }}</span>
      </header>
      <div class="viewer-layout">
        <div class="viewer">
          <ngx-extended-pdf-viewer
            [src]="p.url"
            [(page)]="page"
            [language]="viewerLanguage()"
            [showOpenFileButton]="false"
            [showSecondaryToolbarButton]="false"
            [textLayer]="true"
            [useInlineScripts]="false"
            height="75vh"
            (pageRendered)="onPageRendered($event)"
          />
        </div>
        <aside class="viewer-side">
          <rm-ai-locate-panel [pdfId]="pdfId()" (goTo)="goTo($event)" />
          <section>
            <h3>{{ 'pdfs.search.title' | transloco }}</h3>
            <form (ngSubmit)="search()" class="stack">
              <mat-form-field subscriptSizing="dynamic">
                <mat-label>{{ 'pdfs.search.label' | transloco }}</mat-label>
                <input matInput name="q" [(ngModel)]="query" />
              </mat-form-field>
            </form>
            @if (p.text_status === 'no_text') {
              <p class="notice notice-warn">{{ 'pdfs.search.noText' | transloco }}</p>
            }
            @if (hits(); as list) {
              @if (list.length === 0) {
                <p class="muted">{{ 'pdfs.search.none' | transloco }}</p>
              }
              <ul class="hit-list">
                @for (hit of list; track $index) {
                  <li>
                    <button type="button" class="link" (click)="goTo(hit.page)">
                      {{ 'pdfs.page' | transloco: { page: hit.page } }}
                    </button>
                    {{ hit.snippet }}
                  </li>
                }
              </ul>
            }
          </section>

          <section>
            <h3>
              {{ 'pdfs.annotations.title' | transloco }}
              <span class="term" tabindex="0" [matTooltip]="'glossary.annotation' | transloco"
                >?</span
              >
            </h3>
            @if (canAnnotate()) {
              <p class="muted">{{ 'pdfs.annotations.howTo' | transloco }}</p>
              <mat-form-field subscriptSizing="dynamic">
                <mat-label>{{ 'pdfs.annotations.note' | transloco }}</mat-label>
                <input matInput [(ngModel)]="note" />
              </mat-form-field>
              <button mat-flat-button type="button" [disabled]="busy()" (click)="mark()">
                {{ 'pdfs.annotations.mark' | transloco }}
              </button>
              @if (selectionMissing()) {
                <p class="notice notice-warn" role="status">
                  {{ 'pdfs.annotations.selectFirst' | transloco }}
                </p>
              }
            }
            <ul class="item-list">
              @for (a of annotations(); track a.id) {
                <li>
                  <div>
                    <button type="button" class="link" (click)="show(a)">
                      {{ 'pdfs.page' | transloco: { page: a.page } }}
                    </button>
                    <q>{{ a.quote }}</q>
                    @if (a.note) {
                      <div class="muted">{{ a.note }}</div>
                    }
                  </div>
                  @if (a.user_id === auth.user()?.id || context.isAdmin()) {
                    <button mat-button type="button" (click)="remove(a)">
                      {{ 'common.delete' | transloco }}
                    </button>
                  }
                </li>
              }
            </ul>
          </section>
        </aside>
      </div>
    }
  `,
})
export class PdfViewerPage {
  private readonly api = inject(Api);
  private readonly viewer = inject(NgxExtendedPdfViewerService);
  private readonly transloco = inject(TranslocoService);
  protected readonly auth = inject(AuthService);
  protected readonly context = inject(ProjectContext);

  readonly pdfId = input.required<string>();
  protected readonly pdf = signal<PdfViewOut | null>(null);
  protected readonly annotations = signal<AnnotationOut[]>([]);
  private readonly host = inject(ElementRef<HTMLElement>);
  private readonly active = signal<string | null>(null);
  protected readonly hits = signal<SearchHit[] | null>(null);
  protected readonly error = signal<unknown>(null);
  protected readonly busy = signal(false);
  protected readonly selectionMissing = signal(false);
  protected page = 1;
  protected query = '';
  protected note = '';
  protected readonly canAnnotate = computed(() => {
    const roles = this.context.project()?.my_roles ?? [];
    return roles.some((r) => r === 'admin' || r === 'reviewer' || r === 'extractor');
  });
  protected readonly viewerLanguage = computed(() =>
    this.transloco.getActiveLang() === 'en' ? 'en-US' : 'pt-BR',
  );

  constructor() {
    effect(() => void this.load(this.pdfId()));
    // Saved passages are painted on the pages already rendered whenever they change.
    effect(() => paintAll(this.host.nativeElement, this.annotations(), this.active()));
  }

  protected onPageRendered(event: PageRenderedEvent): void {
    paintPage(this.host.nativeElement, event.pageNumber, this.annotations(), this.active());
  }

  private projectId(): string {
    return this.context.project()!.id;
  }

  private async load(pdfId: string): Promise<void> {
    try {
      const [pdf, annotations] = await Promise.all([
        this.api.invoke(viewPdf, { project_id: this.projectId(), pdf_id: pdfId }),
        this.api.invoke(listAnnotations, { project_id: this.projectId(), pdf_id: pdfId }),
      ]);
      this.pdf.set(pdf);
      this.annotations.set(annotations);
    } catch (error) {
      this.error.set(error);
    }
  }

  protected goTo(page: number): void {
    this.page = page;
  }

  protected show(annotation: AnnotationOut): void {
    this.active.set(annotation.id);
    this.goTo(annotation.page);
    void this.viewer.find(annotation.quote, { highlightAll: false, matchCase: false });
  }

  async search(): Promise<void> {
    if (this.query.trim().length < 2) return;
    try {
      this.hits.set(
        await this.api.invoke(searchPdf, {
          project_id: this.projectId(),
          pdf_id: this.pdfId(),
          q: this.query,
        }),
      );
    } catch (error) {
      this.error.set(error);
    }
  }

  async mark(): Promise<void> {
    const selection = readPdfSelection();
    this.selectionMissing.set(!selection);
    if (!selection) return;
    this.busy.set(true);
    try {
      const created = await this.api.invoke(createAnnotation, {
        project_id: this.projectId(),
        pdf_id: this.pdfId(),
        body: { ...selection, note: this.note || null },
      });
      this.annotations.update((list) => [...list, created].sort((a, b) => a.page - b.page));
      this.note = '';
      window.getSelection()?.removeAllRanges();
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }

  async remove(annotation: AnnotationOut): Promise<void> {
    try {
      await this.api.invoke(deleteAnnotation, {
        project_id: this.projectId(),
        annotation_id: annotation.id,
      });
      this.annotations.update((list) => list.filter((a) => a.id !== annotation.id));
    } catch (error) {
      this.error.set(error);
    }
  }
}
