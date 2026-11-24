import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { decideAiSuggestion } from '../../core/api/fn/ai/decide-ai-suggestion';
import { draftMethodsResults } from '../../core/api/fn/ai/draft-methods-results';
import { DraftOut } from '../../core/api/models/draft-out';
import { withJsonBody } from '../../core/errors/problem';
import { aiFunctionAvailable } from '../../shared/ai-availability';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

/**
 * IA6: draft of Methods and Results. The AI writes with placeholders; the system puts
 * in the PRISMA counts (and, from the meta-analysis screen, the analysis numbers).
 * Any number the AI wrote itself is flagged. The group edits and approves.
 */
@Component({
  selector: 'rm-ai-draft-card',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatSelectModule,
    FormError,
  ],
  template: `
    @if (available()) {
      <mat-card class="block">
        <mat-card-header>
          <mat-card-title
            ><h3>
              <span class="ai-badge">{{ 'tutor.badge' | transloco }}</span>
              {{ 'assist.draft.title' | transloco }}
            </h3></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          <p class="muted">{{ 'assist.draft.intro' | transloco }}</p>
          <div class="row">
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'assist.draft.lang' | transloco }}</mat-label>
              <mat-select [(ngModel)]="lang">
                <mat-option value="pt-BR">Português</mat-option>
                <mat-option value="en">English</mat-option>
              </mat-select>
            </mat-form-field>
            <button mat-stroked-button type="button" [disabled]="busy()" (click)="ask()">
              {{ 'assist.draft.ask' | transloco }}
            </button>
          </div>
          <rm-form-error [error]="error()" />
          @if (draft(); as d) {
            @if (d.unverified.length) {
              <p class="warning" role="alert">
                {{ 'tutor.unverified' | transloco: { items: d.unverified.join(', ') } }}
              </p>
            }
            <h4>{{ 'assist.draft.methods' | transloco }}</h4>
            <p class="draft">{{ d.methods }}</p>
            <h4>{{ 'assist.draft.results' | transloco }}</h4>
            <p class="draft">{{ d.results }}</p>
            <p class="muted small">{{ 'assist.draft.edit' | transloco }}</p>
            <button mat-button type="button" (click)="decide('accepted')">
              {{ 'assist.search.useful' | transloco }}
            </button>
            <button mat-button type="button" (click)="decide('rejected')">
              {{ 'assist.search.notUseful' | transloco }}
            </button>
          }
        </mat-card-content>
      </mat-card>
    }
  `,
  styles: `
    .ai-badge {
      background: var(--mat-sys-primary-container);
      color: var(--mat-sys-on-primary-container);
      border-radius: 4px;
      padding: 0 6px;
      font-size: 0.8em;
    }
    .draft {
      white-space: pre-wrap;
    }
  `,
})
export class AiDraftCard implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  protected readonly available = signal(false);
  protected readonly draft = signal<DraftOut | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected lang: 'pt-BR' | 'en' = 'pt-BR';

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    this.available.set(await aiFunctionAvailable(this.api, this.projectId(), 'draft'));
  }

  async ask(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.draft.set(
        await this.api.invoke(draftMethodsResults, {
          project_id: this.projectId(),
          body: { lang: this.lang },
        }),
      );
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
    }
  }

  async decide(status: 'accepted' | 'rejected'): Promise<void> {
    const d = this.draft();
    if (!d) return;
    try {
      await this.api.invoke(decideAiSuggestion, {
        project_id: this.projectId(),
        suggestion_id: d.suggestion.id,
        body: { status },
      });
    } catch (error) {
      this.error.set(await withJsonBody(error));
    }
  }
}
