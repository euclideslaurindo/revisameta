import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { confirmStudyRobTool } from '../../core/api/fn/risk-of-bias/confirm-study-rob-tool';
import { getStudyRobTool } from '../../core/api/fn/risk-of-bias/get-study-rob-tool';
import { listRobTools } from '../../core/api/fn/risk-of-bias/list-rob-tools';
import { StudyToolOut } from '../../core/api/models/study-tool-out';
import { ToolOut } from '../../core/api/models/tool-out';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { localized } from './rob-tool-editor';

/** Instrument of a study: suggested by the design, confirmed by the admin. */
@Component({
  selector: 'rm-study-rob-tool',
  imports: [
    FormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    FormError,
  ],
  template: `
    @if (state(); as s) {
      @if (tools().length === 0) {
        <p class="muted">
          {{ 'rob.study.noTools' | transloco }}
          <a [routerLink]="['/projetos', projectId(), 'risco-de-vies']">{{
            'rob.study.goToTools' | transloco
          }}</a>
        </p>
      } @else {
        <p>
          @if (s.confirmed) {
            {{ 'rob.study.confirmed' | transloco: { name: toolName(s.tool_id) } }}
          } @else if (s.suggested_tool_id) {
            {{ 'rob.study.suggested' | transloco: { name: toolName(s.suggested_tool_id) } }}
          }
        </p>
        @if (isAdmin()) {
          <div class="row">
            <mat-form-field subscriptSizing="dynamic" class="wide">
              <mat-label>{{ 'rob.study.choose' | transloco }}</mat-label>
              <mat-select [(ngModel)]="choice">
                @for (t of tools(); track t.id) {
                  <mat-option [value]="t.id"
                    >{{ toolName(t.id) }} ({{ t.template_version }})</mat-option
                  >
                }
              </mat-select>
            </mat-form-field>
            <button
              mat-flat-button
              type="button"
              [disabled]="busy() || !choice"
              (click)="confirm()"
            >
              {{ 'rob.study.confirm' | transloco }}
            </button>
          </div>
        }
      }
    }
    <rm-form-error [error]="error()" />
  `,
})
export class StudyRobTool implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);
  private readonly lang = toSignal(inject(TranslocoService).langChanges$, {
    initialValue: 'pt-BR',
  });

  readonly studyId = input.required<string>();
  protected readonly state = signal<StudyToolOut | null>(null);
  protected readonly tools = signal<ToolOut[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly isAdmin = computed(() => this.context.isAdmin());
  protected readonly projectId = computed(() => this.context.project()!.id);
  protected choice: string | null = null;

  async ngOnInit(): Promise<void> {
    try {
      const project_id = this.projectId();
      const [state, tools] = await Promise.all([
        this.api.invoke(getStudyRobTool, { project_id, study_id: this.studyId() }),
        this.api.invoke(listRobTools, { project_id }),
      ]);
      this.tools.set(tools);
      this.set(state);
    } catch (error) {
      this.error.set(error);
    }
  }

  private set(state: StudyToolOut): void {
    this.state.set(state);
    this.choice = state.tool_id ?? state.suggested_tool_id ?? null;
  }

  protected toolName(id: string | null | undefined): string {
    const tool = this.tools().find((t) => t.id === id);
    return tool ? localized(tool.structure['name'] as Record<string, string>, this.lang()) : '—';
  }

  async confirm(): Promise<void> {
    if (!this.choice) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      this.set(
        await this.api.invoke(confirmStudyRobTool, {
          project_id: this.projectId(),
          study_id: this.studyId(),
          body: { tool_id: this.choice },
        }),
      );
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
