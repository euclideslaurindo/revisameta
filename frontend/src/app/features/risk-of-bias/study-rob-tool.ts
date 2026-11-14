import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { confirmStudyRobTool } from '../../core/api/fn/risk-of-bias/confirm-study-rob-tool';
import { getStudyRobTool } from '../../core/api/fn/risk-of-bias/get-study-rob-tool';
import { listRobAssessments } from '../../core/api/fn/risk-of-bias/list-rob-assessments';
import { listRobTools } from '../../core/api/fn/risk-of-bias/list-rob-tools';
import { startRobAssessment } from '../../core/api/fn/risk-of-bias/start-rob-assessment';
import { listOutcomes } from '../../core/api/fn/protocol/list-outcomes';
import { AssessmentSummary } from '../../core/api/models/assessment-summary';
import { OutcomeOut } from '../../core/api/models/outcome-out';
import { StudyToolOut } from '../../core/api/models/study-tool-out';
import { ToolOut } from '../../core/api/models/tool-out';
import { AuthService } from '../../core/auth/auth';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { localized } from './rob-tool-editor';

/** Risk of bias of a study: its instrument (suggested by design, confirmed by the admin) and assessments. */
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
        @if (isAdmin() && assessments().length === 0) {
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

        @if (assessments().length) {
          <ul class="item-list">
            @for (a of assessments(); track a.id) {
              <li>
                <div>
                  <a [routerLink]="['/projetos', projectId(), 'risco-de-vies', 'avaliacoes', a.id]">
                    {{
                      a.kind === 'individual'
                        ? a.reviewer_name
                        : ('rob.study.consensus' | transloco)
                    }}
                  </a>
                  @if (a.timepoint) {
                    <span class="muted">
                      · {{ outcomeName(a.outcome_id) }} · {{ a.timepoint }}</span
                    >
                  }
                  <span class="badge">{{ 'extraction.status.' + a.status | transloco }}</span>
                </div>
              </li>
            }
          </ul>
        }

        @if (isAdmin() && assessments().length) {
          <a
            mat-stroked-button
            [routerLink]="[
              '/projetos',
              projectId(),
              'risco-de-vies',
              'estudos',
              studyId(),
              'consenso',
            ]"
          >
            {{ 'rob.study.compare' | transloco }}
          </a>
        }

        @if (s.confirmed && canAssess()) {
          @if (perResult()) {
            <p class="muted">{{ 'rob.study.perResult' | transloco }}</p>
            <div class="row">
              <mat-form-field subscriptSizing="dynamic">
                <mat-label>{{ 'rob.study.outcome' | transloco }}</mat-label>
                <mat-select [(ngModel)]="outcomeId">
                  @for (o of outcomes(); track o.id) {
                    <mat-option [value]="o.id">{{ o.name }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
              <mat-form-field subscriptSizing="dynamic">
                <mat-label>{{ 'rob.study.timepoint' | transloco }}</mat-label>
                <mat-select [(ngModel)]="timepoint">
                  @for (t of timepointsOf(outcomeId); track t) {
                    <mat-option [value]="t">{{ t }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
            </div>
          }
          <button mat-flat-button type="button" [disabled]="busy()" (click)="start()">
            {{ 'rob.study.start' | transloco }}
          </button>
        }
      }
    }
    <rm-form-error [error]="error()" />
  `,
})
export class StudyRobTool implements OnInit {
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);
  private readonly context = inject(ProjectContext);
  private readonly lang = toSignal(inject(TranslocoService).langChanges$, {
    initialValue: 'pt-BR',
  });

  readonly studyId = input.required<string>();
  protected readonly state = signal<StudyToolOut | null>(null);
  protected readonly tools = signal<ToolOut[]>([]);
  protected readonly assessments = signal<AssessmentSummary[]>([]);
  protected readonly outcomes = signal<OutcomeOut[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly isAdmin = computed(() => this.context.isAdmin());
  protected readonly canAssess = computed(() => {
    const roles = this.context.project()?.my_roles ?? [];
    return roles.includes('admin') || roles.includes('reviewer');
  });
  protected readonly projectId = computed(() => this.context.project()!.id);
  protected readonly perResult = computed(() => {
    const tool = this.tools().find((t) => t.id === this.state()?.tool_id);
    return tool?.structure['scope'] === 'result';
  });
  protected choice: string | null = null;
  protected outcomeId: string | null = null;
  protected timepoint: string | null = null;

  async ngOnInit(): Promise<void> {
    try {
      const project_id = this.projectId();
      const [state, tools, assessments, outcomes] = await Promise.all([
        this.api.invoke(getStudyRobTool, { project_id, study_id: this.studyId() }),
        this.api.invoke(listRobTools, { project_id }),
        this.api.invoke(listRobAssessments, { project_id, study_id: this.studyId() }),
        this.api.invoke(listOutcomes, { project_id }),
      ]);
      this.tools.set(tools);
      this.assessments.set(assessments);
      this.outcomes.set(outcomes);
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

  protected outcomeName(id: string | null | undefined): string {
    return this.outcomes().find((o) => o.id === id)?.name ?? '';
  }

  protected timepointsOf(id: string | null): string[] {
    return this.outcomes().find((o) => o.id === id)?.timepoints ?? [];
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

  async start(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const body = this.perResult()
        ? { outcome_id: this.outcomeId, timepoint: this.timepoint }
        : {};
      const assessment = await this.api.invoke(startRobAssessment, {
        project_id: this.projectId(),
        study_id: this.studyId(),
        body,
      });
      await this.router.navigate([
        '/projetos',
        this.projectId(),
        'risco-de-vies',
        'avaliacoes',
        assessment.id,
      ]);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
