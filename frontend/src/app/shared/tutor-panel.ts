import { Component, OnInit, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../core/api/api';
import { aiSettings } from '../core/api/fn/ai/ai-settings';
import { askTutor } from '../core/api/fn/ai/ask-tutor';
import { RunIn } from '../core/api/models/run-in';
import { TutorOut } from '../core/api/models/tutor-out';
import { withJsonBody } from '../core/errors/problem';
import { ProjectContext } from '../features/project/project-context';
import { FormError } from './form-error';

/**
 * AI tutor (IA1). Explains; never decides or computes. Numbers in the answer come from
 * R; any number the AI wrote by itself is listed as "not verified".
 */
@Component({
  selector: 'rm-tutor-panel',
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
      <section class="ai-box" [attr.aria-label]="'tutor.title' | transloco">
        <h3>
          <span class="ai-badge">{{ 'tutor.badge' | transloco }}</span>
          {{ 'tutor.title' | transloco }}
        </h3>
        <p class="muted">{{ 'tutor.intro' | transloco }}</p>
        <mat-form-field subscriptSizing="dynamic" class="full">
          <mat-label>{{ 'tutor.question' | transloco }}</mat-label>
          <textarea matInput rows="2" maxlength="1000" [(ngModel)]="question"></textarea>
        </mat-form-field>
        <button
          mat-stroked-button
          type="button"
          [disabled]="busy() || question.trim().length < 3"
          (click)="ask()"
        >
          {{ 'tutor.ask' | transloco }}
        </button>
        <rm-form-error [error]="error()" />
        @if (answer(); as a) {
          <div class="answer" role="status">
            <p>{{ a.text }}</p>
            @if (a.unverified.length) {
              <p class="warning">
                {{ 'tutor.unverified' | transloco: { items: a.unverified.join(', ') } }}
              </p>
            }
            <p class="muted small">
              {{
                'tutor.source'
                  | transloco: { provider: a.provider, model: a.model, version: a.prompt_version }
              }}
            </p>
          </div>
        }
      </section>
    }
  `,
  styles: `
    .ai-box {
      border: 1px dashed var(--mat-sys-primary);
      border-radius: 8px;
      padding: 8px 16px;
      margin: 16px 0;
    }
    .ai-badge {
      background: var(--mat-sys-primary-container);
      color: var(--mat-sys-on-primary-container);
      border-radius: 4px;
      padding: 0 6px;
      font-size: 0.8em;
    }
    .full {
      width: 100%;
    }
  `,
})
export class TutorPanel implements OnInit {
  private readonly api = inject(Api);
  private readonly transloco = inject(TranslocoService);
  private readonly context = inject(ProjectContext);

  /** The analysis on screen; null for a concept question. */
  readonly analysis = input<RunIn | null>(null);

  protected readonly available = signal(false);
  protected question = '';

  async ngOnInit(): Promise<void> {
    try {
      const s = await this.api.invoke(aiSettings, { project_id: this.context.project()!.id });
      this.available.set(
        s.enabled && s.functions.includes('tutor') && !s.disabled_functions['tutor'],
      );
    } catch {
      this.available.set(false);
    }
  }

  protected readonly answer = signal<TutorOut | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);

  async ask(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.answer.set(
        await this.api.invoke(askTutor, {
          project_id: this.context.project()!.id,
          body: {
            question: this.question.trim(),
            lang: this.transloco.getActiveLang().startsWith('en') ? 'en' : 'pt-BR',
            analysis: this.analysis(),
          },
        }),
      );
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
    }
  }
}
