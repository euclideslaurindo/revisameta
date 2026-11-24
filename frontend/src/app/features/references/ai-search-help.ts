import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { decideAiSuggestion } from '../../core/api/fn/ai/decide-ai-suggestion';
import { searchStrategyHelp } from '../../core/api/fn/ai/search-strategy-help';
import { SearchHelpOut } from '../../core/api/models/search-help-out';
import { withJsonBody } from '../../core/errors/problem';
import { aiFunctionAvailable } from '../../shared/ai-availability';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

/** IA5: MeSH/DeCS terms and a PubMed query from the protocol, for a person to review. */
@Component({
  selector: 'rm-ai-search-help',
  imports: [TranslocoPipe, MatButtonModule, FormError],
  template: `
    @if (available()) {
      <section class="ai-box">
        <h3>
          <span class="ai-badge">{{ 'tutor.badge' | transloco }}</span>
          {{ 'assist.search.title' | transloco }}
        </h3>
        <p class="muted">{{ 'assist.search.intro' | transloco }}</p>
        <button mat-stroked-button type="button" [disabled]="busy()" (click)="ask()">
          {{ 'assist.search.ask' | transloco }}
        </button>
        <rm-form-error [error]="error()" />
        @if (help(); as h) {
          <table class="result-table">
            <thead>
              <tr>
                <th scope="col">{{ 'assist.search.concept' | transloco }}</th>
                <th scope="col">MeSH</th>
                <th scope="col">DeCS</th>
                <th scope="col">{{ 'assist.search.free' | transloco }}</th>
              </tr>
            </thead>
            <tbody>
              @for (c of h.concepts; track $index) {
                <tr>
                  <td>{{ c.concept }}</td>
                  <td>{{ (c.mesh ?? []).join('; ') }}</td>
                  <td>{{ (c.decs ?? []).join('; ') }}</td>
                  <td>{{ (c.free_text ?? []).join('; ') }}</td>
                </tr>
              }
            </tbody>
          </table>
          <h4>PubMed</h4>
          <pre class="query">{{ h.pubmed }}</pre>
          <p class="warning">{{ 'assist.search.review' | transloco }}</p>
          <button mat-button type="button" (click)="decide('accepted')">
            {{ 'assist.search.useful' | transloco }}
          </button>
          <button mat-button type="button" (click)="decide('rejected')">
            {{ 'assist.search.notUseful' | transloco }}
          </button>
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
    .query {
      white-space: pre-wrap;
      word-break: break-word;
    }
  `,
})
export class AiSearchHelp implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  protected readonly available = signal(false);
  protected readonly help = signal<SearchHelpOut | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    this.available.set(await aiFunctionAvailable(this.api, this.projectId(), 'search'));
  }

  async ask(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.help.set(await this.api.invoke(searchStrategyHelp, { project_id: this.projectId() }));
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
    }
  }

  async decide(status: 'accepted' | 'rejected'): Promise<void> {
    const h = this.help();
    if (!h) return;
    try {
      await this.api.invoke(decideAiSuggestion, {
        project_id: this.projectId(),
        suggestion_id: h.suggestion.id,
        body: { status },
      });
    } catch (error) {
      this.error.set(await withJsonBody(error));
    }
  }
}
