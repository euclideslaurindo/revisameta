import { Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { aiSettings } from '../../core/api/fn/ai/ai-settings';
import { aiSuggestions } from '../../core/api/fn/ai/ai-suggestions';
import { decideAiSuggestion } from '../../core/api/fn/ai/decide-ai-suggestion';
import { locatePassages } from '../../core/api/fn/ai/locate-passages';
import { LocateOut } from '../../core/api/models/locate-out';
import { SuggestionOut } from '../../core/api/models/suggestion-out';
import { withJsonBody } from '../../core/errors/problem';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

/**
 * Passage finder (IA2). The AI points at passages; every quote was checked against
 * the PDF text by the server. The person reads the page and marks if it helped.
 */
@Component({
  selector: 'rm-ai-locate-panel',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    FormError,
  ],
  template: `
    @if (available()) {
      <section class="ai-box">
        <h3>
          <span class="ai-badge">{{ 'tutor.badge' | transloco }}</span>
          {{ 'locate.title' | transloco }}
        </h3>
        <p class="muted">{{ 'locate.intro' | transloco }}</p>
        <form (ngSubmit)="ask()" class="stack">
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'locate.question' | transloco }}</mat-label>
            <input matInput name="aiq" maxlength="500" [(ngModel)]="question" />
          </mat-form-field>
          <button
            mat-stroked-button
            type="submit"
            [disabled]="busy() || question.trim().length < 3"
          >
            {{ 'locate.ask' | transloco }}
          </button>
        </form>
        <rm-form-error [error]="error()" />
        @if (last(); as l) {
          @if (l.discarded) {
            <p class="warning" role="status">
              {{ 'locate.discarded' | transloco: { n: l.discarded } }}
            </p>
          }
          @if (!l.suggestions.length) {
            <p class="muted">{{ 'locate.none' | transloco }}</p>
          }
        }
        <ul class="hit-list">
          @for (s of items(); track s.id) {
            <li>
              <button type="button" class="link" (click)="goTo.emit(s.page ?? 1)">
                {{ 'pdfs.page' | transloco: { page: s.page } }}
              </button>
              <q>{{ s.quote }}</q>
              <div class="muted small">{{ s.question }}</div>
              @if (s.status === 'suggested') {
                <button mat-button type="button" (click)="decide(s, 'accepted')">
                  {{ 'locate.useful' | transloco }}
                </button>
                <button mat-button type="button" (click)="decide(s, 'rejected')">
                  {{ 'locate.notUseful' | transloco }}
                </button>
              } @else {
                <span class="badge">{{ 'locate.status.' + s.status | transloco }}</span>
              }
            </li>
          }
        </ul>
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
export class AiLocatePanel implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  readonly pdfId = input.required<string>();
  readonly goTo = output<number>();

  protected readonly available = signal(false);
  protected readonly items = signal<SuggestionOut[]>([]);
  protected readonly last = signal<LocateOut | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected question = '';

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    try {
      const s = await this.api.invoke(aiSettings, { project_id: this.projectId() });
      this.available.set(
        s.enabled && s.functions.includes('locate') && !s.disabled_functions['locate'],
      );
      if (this.available()) await this.reload();
    } catch {
      this.available.set(false);
    }
  }

  private async reload(): Promise<void> {
    this.items.set(
      await this.api.invoke(aiSuggestions, {
        project_id: this.projectId(),
        target_id: this.pdfId(),
      }),
    );
  }

  async ask(): Promise<void> {
    await this.guard(async () => {
      this.last.set(
        await this.api.invoke(locatePassages, {
          project_id: this.projectId(),
          body: { pdf_id: this.pdfId(), question: this.question.trim() },
        }),
      );
      await this.reload();
    });
  }

  async decide(s: SuggestionOut, status: 'accepted' | 'rejected'): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(decideAiSuggestion, {
        project_id: this.projectId(),
        suggestion_id: s.id,
        body: { status },
      });
      await this.reload();
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
