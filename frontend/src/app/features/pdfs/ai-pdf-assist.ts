import { Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { decideAiSuggestion } from '../../core/api/fn/ai/decide-ai-suggestion';
import { robSecondOpinion } from '../../core/api/fn/ai/rob-second-opinion';
import { suggestExtraction } from '../../core/api/fn/ai/suggest-extraction';
import { ExtractOut } from '../../core/api/models/extract-out';
import { RobHintOut } from '../../core/api/models/rob-hint-out';
import { SuggestionOut } from '../../core/api/models/suggestion-out';
import { withJsonBody } from '../../core/errors/problem';
import { aiFunctionAvailable } from '../../shared/ai-availability';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

const ANSWERS = ['Y', 'PY', 'PN', 'N', 'NI', 'NA'];

/**
 * IA3 (values to extract) and IA4 (risk-of-bias second opinion) next to the PDF. The AI
 * only points at printed values and passages, all checked by the server; people type
 * every value and choose every answer themselves.
 */
@Component({
  selector: 'rm-ai-pdf-assist',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    FormError,
  ],
  template: `
    @if (canExtract() || canRob()) {
      <section class="ai-box">
        <rm-form-error [error]="error()" />
        @if (canExtract()) {
          <h3>
            <span class="ai-badge">{{ 'tutor.badge' | transloco }}</span>
            {{ 'assist.extract.title' | transloco }}
          </h3>
          <p class="muted">{{ 'assist.extract.intro' | transloco }}</p>
          <form (ngSubmit)="extract()" class="stack">
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'assist.extract.request' | transloco }}</mat-label>
              <input matInput name="req" maxlength="500" [(ngModel)]="request" />
            </mat-form-field>
            <button
              mat-stroked-button
              type="submit"
              [disabled]="busy() || request.trim().length < 3"
            >
              {{ 'assist.extract.ask' | transloco }}
            </button>
          </form>
          @if (extracted(); as x) {
            @if (x.dispersion_warning) {
              <p class="warning" role="alert">
                {{ 'assist.extract.dispersion' | transloco }} {{ x.dispersion_warning }}
              </p>
            }
            @if (x.discarded) {
              <p class="warning">{{ 'assist.discarded' | transloco: { n: x.discarded } }}</p>
            }
            <ul class="hit-list">
              @for (s of x.suggestions; track s.id) {
                <li>
                  <strong>{{ field(s) }} = {{ value(s) }}</strong>
                  <button type="button" class="link" (click)="goTo.emit(s.page ?? 1)">
                    {{ 'pdfs.page' | transloco: { page: s.page } }}
                  </button>
                  <q>{{ s.quote }}</q>
                  <div>
                    <button mat-button type="button" (click)="decide(s, 'accepted')">
                      {{ 'assist.extract.used' | transloco }}
                    </button>
                    <button mat-button type="button" (click)="decide(s, 'rejected')">
                      {{ 'assist.extract.wrong' | transloco }}
                    </button>
                  </div>
                </li>
              }
            </ul>
          }
        }
        @if (canRob()) {
          <h3>
            <span class="ai-badge">{{ 'tutor.badge' | transloco }}</span>
            {{ 'assist.rob.title' | transloco }}
          </h3>
          <p class="muted">{{ 'assist.rob.intro' | transloco }}</p>
          <form (ngSubmit)="rob()" class="stack">
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'assist.rob.question' | transloco }}</mat-label>
              <textarea
                matInput
                name="robq"
                rows="2"
                maxlength="1000"
                [(ngModel)]="question"
              ></textarea>
            </mat-form-field>
            <button
              mat-stroked-button
              type="submit"
              [disabled]="busy() || question.trim().length < 5"
            >
              {{ 'assist.rob.ask' | transloco }}
            </button>
          </form>
          @if (hint(); as h) {
            @if (h.discarded) {
              <p class="warning">{{ 'assist.rob.discarded' | transloco }}</p>
            } @else if (h.suggestion; as s) {
              <p>
                <strong>{{ 'rob.answer.' + answer(s) | transloco }}</strong> — {{ h.reason }}
              </p>
              @if (s.quote) {
                <button type="button" class="link" (click)="goTo.emit(s.page ?? 1)">
                  {{ 'pdfs.page' | transloco: { page: s.page } }}
                </button>
                <q>{{ s.quote }}</q>
              }
            }
          }
        }
      </section>
    }
  `,
  styles: `
    .ai-box {
      border: 1px dashed var(--mat-sys-primary);
      border-radius: 8px;
      padding: 8px 12px;
      margin: 12px 0;
    }
    .ai-badge {
      background: var(--mat-sys-primary-container);
      color: var(--mat-sys-on-primary-container);
      border-radius: 4px;
      padding: 0 6px;
      font-size: 0.8em;
    }
  `,
})
export class AiPdfAssist implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  readonly pdfId = input.required<string>();
  readonly goTo = output<number>();

  protected readonly canExtract = signal(false);
  protected readonly canRob = signal(false);
  protected readonly extracted = signal<ExtractOut | null>(null);
  protected readonly hint = signal<RobHintOut | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected request = '';
  protected question = '';

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    this.canExtract.set(await aiFunctionAvailable(this.api, this.projectId(), 'extract'));
    this.canRob.set(await aiFunctionAvailable(this.api, this.projectId(), 'rob'));
  }

  protected field(s: SuggestionOut): string {
    return String(s.payload['field'] ?? '');
  }

  protected value(s: SuggestionOut): string {
    return String(s.payload['value'] ?? '');
  }

  protected answer(s: SuggestionOut): string {
    const a = String(s.payload['answer'] ?? '');
    return ANSWERS.includes(a) ? a : 'NI';
  }

  async extract(): Promise<void> {
    await this.guard(async () =>
      this.extracted.set(
        await this.api.invoke(suggestExtraction, {
          project_id: this.projectId(),
          body: { pdf_id: this.pdfId(), request: this.request.trim() },
        }),
      ),
    );
  }

  async rob(): Promise<void> {
    await this.guard(async () =>
      this.hint.set(
        await this.api.invoke(robSecondOpinion, {
          project_id: this.projectId(),
          body: { pdf_id: this.pdfId(), question: this.question.trim(), options: ANSWERS },
        }),
      ),
    );
  }

  async decide(s: SuggestionOut, status: 'accepted' | 'rejected'): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(decideAiSuggestion, {
        project_id: this.projectId(),
        suggestion_id: s.id,
        body: { status },
      });
    });
  }

  private async guard(action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await action();
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
    }
  }
}
