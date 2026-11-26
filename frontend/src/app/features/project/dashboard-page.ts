import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { Skeleton } from '../../shared/skeleton';

import { Api } from '../../core/api/api';
import { projectDashboard } from '../../core/api/fn/dashboard/project-dashboard';
import { DashboardOut } from '../../core/api/models/dashboard-out';
import { StageOut } from '../../core/api/models/stage-out';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from './project-context';

/** First screen of a project: where each stage stands, what is next and who has work left. */
@Component({
  selector: 'rm-dashboard-page',
  imports: [
    Skeleton,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatProgressBarModule,
    FormError,
  ],
  template: `
    <rm-form-error [error]="error()" />
    @if (data(); as d) {
      @if (d.days_left !== null && d.days_left !== undefined) {
        <p
          class="notice"
          [class.notice-error]="d.days_left < 0"
          [class.notice-warn]="d.days_left >= 0 && d.days_left <= 14"
          role="status"
        >
          @if (d.days_left > 0) {
            {{ 'dashboard.daysLeft' | transloco: { days: d.days_left } }}
          } @else if (d.days_left === 0) {
            {{ 'dashboard.today' | transloco }}
          } @else {
            {{ 'dashboard.late' | transloco: { days: -d.days_left } }}
          }
        </p>
      } @else {
        <p class="muted">{{ 'dashboard.noDeadline' | transloco }}</p>
      }

      @if (firstSteps(d); as steps) {
        <mat-card class="block first-steps">
          <mat-card-content>
            <h3>{{ 'dashboard.first.title' | transloco }}</h3>
            <p class="muted">{{ 'dashboard.first.intro' | transloco }}</p>
            <ol class="checklist">
              @for (step of steps; track step.key) {
                <li [class.done]="step.done">
                  <span class="check-mark" aria-hidden="true">{{ step.done ? '✓' : '' }}</span>
                  <span class="sr-only">{{
                    (step.done ? 'dashboard.first.doneLabel' : 'dashboard.first.todoLabel')
                      | transloco
                  }}</span>
                  <a [routerLink]="['..', step.route]">{{
                    'dashboard.first.' + step.key | transloco
                  }}</a>
                  @if (step.optional) {
                    <span class="muted small">({{ 'dashboard.first.optional' | transloco }})</span>
                  }
                </li>
              }
            </ol>
          </mat-card-content>
        </mat-card>
      }

      @if (next(d); as n) {
        <mat-card class="block">
          <mat-card-content>
            <h3>{{ 'dashboard.nextTitle' | transloco }}</h3>
            <p>{{ 'dashboard.next.' + n.key | transloco }}</p>
            <a mat-flat-button [routerLink]="['..', n.route]">{{
              'dashboard.go' | transloco: { stage: ('dashboard.stage.' + n.key | transloco) }
            }}</a>
          </mat-card-content>
        </mat-card>
      } @else {
        <p class="notice notice-ok" role="status">{{ 'dashboard.allDone' | transloco }}</p>
      }

      <mat-card class="block">
        <mat-card-header
          ><mat-card-title
            ><h3>{{ 'dashboard.stagesTitle' | transloco }}</h3></mat-card-title
          ></mat-card-header
        >
        <mat-card-content>
          <ul class="item-list">
            @for (s of d.stages; track s.key) {
              <li class="stage-row">
                <div>
                  <a [routerLink]="['..', s.route]"
                    ><strong>{{ 'dashboard.stage.' + s.key | transloco }}</strong></a
                  >
                  <span class="badge" [class.badge-block]="s.state !== 'done'">{{
                    'dashboard.state.' + s.state | transloco
                  }}</span>
                  <div class="muted">
                    {{ 'dashboard.count.' + s.key | transloco: { done: s.done, total: s.total } }}
                  </div>
                </div>
                <mat-progress-bar
                  mode="determinate"
                  [value]="percent(s)"
                  [attr.aria-label]="'dashboard.stage.' + s.key | transloco"
                />
              </li>
            }
          </ul>
        </mat-card-content>
      </mat-card>

      <mat-card class="block">
        <mat-card-header
          ><mat-card-title
            ><h3>{{ 'dashboard.peopleTitle' | transloco }}</h3></mat-card-title
          ></mat-card-header
        >
        <mat-card-content>
          <p class="muted">{{ 'dashboard.peopleHint' | transloco }}</p>
          <div class="table-scroll">
            <table class="sample">
              <thead>
                <tr>
                  <th>{{ 'dashboard.person' | transloco }}</th>
                  <th>{{ 'dashboard.screeningLeft' | transloco }}</th>
                  <th>{{ 'dashboard.extractionsOpen' | transloco }}</th>
                  <th>{{ 'dashboard.robOpen' | transloco }}</th>
                </tr>
              </thead>
              <tbody>
                @for (p of d.people; track p.user_id) {
                  <tr>
                    <td>{{ p.name }}</td>
                    <td>{{ p.screening_left }}</td>
                    <td>{{ p.extractions_open }}</td>
                    <td>{{ p.rob_open }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </mat-card-content>
      </mat-card>
    } @else if (!error()) {
      <rm-skeleton [lines]="[90, 140, 220]" />
    }
  `,
  styles: `
    .stage-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(120px, 30%);
      gap: 1rem;
      align-items: center;
    }
  `,
})
export class DashboardPage implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  /** "First steps" checklist (front A): shown until the project's basics are in place. */
  protected firstSteps(
    d: DashboardOut,
  ): { key: string; route: string; done: boolean; optional?: boolean }[] | null {
    const project = this.context.project();
    const protocol = d.stages.find((s) => s.key === 'protocol');
    const steps = [
      { key: 'question', route: 'protocolo', done: !!project?.question },
      { key: 'protocol', route: 'protocolo', done: protocol?.state === 'done' },
      { key: 'team', route: 'configuracoes', done: d.people.length > 1, optional: true },
      { key: 'studies', route: 'estudos', done: d.studies > 0 },
    ];
    return steps.filter((x) => !x.optional).every((x) => x.done) ? null : steps;
  }
  protected readonly data = signal<DashboardOut | null>(null);
  protected readonly error = signal<unknown>(null);

  async ngOnInit(): Promise<void> {
    try {
      this.data.set(
        await this.api.invoke(projectDashboard, { project_id: this.context.project()!.id }),
      );
    } catch (error) {
      this.error.set(error);
    }
  }

  protected next(d: DashboardOut): StageOut | undefined {
    return d.stages.find((s) => s.key === d.next_stage);
  }

  /** Bar length only; the numbers shown are the counts themselves. */
  protected percent(s: StageOut): number {
    return s.total ? Math.round((100 * s.done) / s.total) : 0;
  }
}
