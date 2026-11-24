import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { aiMetrics } from '../../core/api/fn/ai/ai-metrics';
import { aiStatement } from '../../core/api/fn/ai/ai-statement';
import { TaskMetrics } from '../../core/api/models/task-metrics';
import { withJsonBody } from '../../core/errors/problem';
import { fileNameFrom, saveFile } from '../../shared/download';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from './project-context';

/** Accuracy of each AI feature against people's decisions, and the AI-use statement. */
@Component({
  selector: 'rm-ai-metrics',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    FormError,
  ],
  template: `
    <h3>{{ 'settings.metrics.title' | transloco }}</h3>
    <p class="muted">{{ 'settings.metrics.intro' | transloco }}</p>
    <rm-form-error [error]="error()" />
    <table class="result-table">
      <thead>
        <tr>
          <th scope="col">{{ 'settings.metrics.task' | transloco }}</th>
          <th scope="col">{{ 'settings.metrics.decided' | transloco }}</th>
          <th scope="col">{{ 'settings.metrics.accuracy' | transloco }}</th>
          <th scope="col">{{ 'settings.metrics.discarded' | transloco }}</th>
        </tr>
      </thead>
      <tbody>
        @for (m of tasks(); track m.task) {
          <tr>
            <td>{{ 'settings.ai.fn.' + m.task | transloco }}</td>
            <td>{{ m.decided }}</td>
            <td>
              @if (m.accuracy === null || m.accuracy === undefined) {
                {{ 'settings.metrics.notYet' | transloco: { n: m.min_decided } }}
              } @else {
                {{ percent(m.accuracy) }}%
                @if (m.disabled) {
                  <span class="badge badge-block">{{ 'settings.metrics.off' | transloco }}</span>
                }
              }
            </td>
            <td>{{ m.discarded }}</td>
          </tr>
        }
      </tbody>
    </table>
    <div class="row">
      <mat-form-field subscriptSizing="dynamic">
        <mat-label>{{ 'settings.metrics.lang' | transloco }}</mat-label>
        <mat-select [(ngModel)]="lang">
          <mat-option value="pt-BR">Português</mat-option>
          <mat-option value="en">English</mat-option>
        </mat-select>
      </mat-form-field>
      <button mat-stroked-button type="button" (click)="statement()">
        {{ 'settings.metrics.statement' | transloco }}
      </button>
    </div>
  `,
})
export class AiMetrics implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  protected readonly tasks = signal<TaskMetrics[]>([]);
  protected readonly error = signal<unknown>(null);
  protected lang: 'pt-BR' | 'en' = 'pt-BR';

  async ngOnInit(): Promise<void> {
    try {
      const out = await this.api.invoke(aiMetrics, { project_id: this.context.project()!.id });
      this.tasks.set(out.tasks);
    } catch (error) {
      this.error.set(await withJsonBody(error));
    }
  }

  protected percent(value: number): number {
    return Math.round(value * 100);
  }

  async statement(): Promise<void> {
    try {
      const response = await this.api.invoke$Response(aiStatement, {
        project_id: this.context.project()!.id,
        lang: this.lang,
      });
      saveFile(response.body, fileNameFrom(response.headers.get('content-disposition'), 'ai.docx'));
    } catch (error) {
      this.error.set(await withJsonBody(error));
    }
  }
}
