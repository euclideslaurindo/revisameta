import { Component, inject, OnInit, signal } from '@angular/core';
import {
  FormGroupDirective,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';
import { ReadonlyNote } from '../../shared/readonly-note';

import { Api } from '../../core/api/api';
import { updateProject } from '../../core/api/fn/projects/update-project';
import { createGroup } from '../../core/api/fn/protocol/create-group';
import { createOutcome } from '../../core/api/fn/protocol/create-outcome';
import { deleteGroup } from '../../core/api/fn/protocol/delete-group';
import { deleteOutcome } from '../../core/api/fn/protocol/delete-outcome';
import { listGroups } from '../../core/api/fn/protocol/list-groups';
import { listOutcomes } from '../../core/api/fn/protocol/list-outcomes';
import { GroupOut } from '../../core/api/models/group-out';
import { OutcomeOut } from '../../core/api/models/outcome-out';
import { ConfirmDialog, ConfirmData } from '../../shared/confirm-dialog';
import { FormError } from '../../shared/form-error';
import { AnalysisPlanEditor } from './analysis-plan-editor';
import { FormEditor } from './form-editor';
import { ProjectDetails } from './project-details';
import { ProjectContext } from '../project/project-context';

@Component({
  selector: 'rm-protocol-page',
  imports: [
    ReadonlyNote,
    ReactiveFormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatChipsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatTooltipModule,
    FormError,
    FormEditor,
    AnalysisPlanEditor,
    ProjectDetails,
  ],
  template: `
    <p class="muted">{{ 'protocol.intro' | transloco }}</p>
    <rm-readonly-note />
    <rm-form-error [error]="error()" />

    <rm-project-details />

    @if (context.project(); as project) {
      <mat-card class="block">
        <mat-card-header>
          <mat-card-title>
            <h2>
              {{ 'protocol.doubleExtraction.title' | transloco }}
              <span class="term" tabindex="0" [matTooltip]="'glossary.doubleExtraction' | transloco"
                >?</span
              >
            </h2>
          </mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <mat-slide-toggle
            [checked]="project.double_extraction"
            [disabled]="!context.isAdmin() || busy()"
            (change)="setDoubleExtraction($event.checked)"
          >
            {{
              (project.double_extraction
                ? 'protocol.doubleExtraction.on'
                : 'protocol.doubleExtraction.off'
              ) | transloco
            }}
          </mat-slide-toggle>
          <h3>{{ 'protocol.doubleRob.title' | transloco }}</h3>
          <mat-slide-toggle
            [checked]="project.double_rob"
            [disabled]="!context.isAdmin() || busy()"
            (change)="setDoubleRob($event.checked)"
          >
            {{
              (project.double_rob ? 'protocol.doubleRob.on' : 'protocol.doubleRob.off') | transloco
            }}
          </mat-slide-toggle>
        </mat-card-content>
      </mat-card>
    }

    <mat-card class="block">
      <mat-card-header>
        <mat-card-title>
          <h2>
            {{ 'protocol.outcomes.title' | transloco }}
            <span class="term" tabindex="0" [matTooltip]="'glossary.outcome' | transloco">?</span>
          </h2>
        </mat-card-title>
      </mat-card-header>
      <mat-card-content>
        @if (outcomes().length === 0) {
          <p class="empty">{{ 'protocol.outcomes.empty' | transloco }}</p>
        }
        <ul class="item-list">
          @for (outcome of outcomes(); track outcome.id) {
            <li>
              <div>
                <strong>{{ outcome.name }}</strong>
                @if (outcome.is_primary) {
                  <span class="badge">{{ 'protocol.outcomes.primary' | transloco }}</span>
                }
                <div class="muted">
                  {{ 'protocol.outcomes.types.' + outcome.type | transloco }} ·
                  {{
                    (outcome.higher_is_better
                      ? 'protocol.outcomes.higherBetter'
                      : 'protocol.outcomes.higherWorse'
                    ) | transloco
                  }}
                  @if (outcome.timepoints.length) {
                    · {{ outcome.timepoints.join(', ') }}
                  }
                </div>
              </div>
              @if (context.isAdmin()) {
                <button mat-button type="button" (click)="removeOutcome(outcome)">
                  {{ 'common.delete' | transloco }}
                </button>
              }
            </li>
          }
        </ul>

        @if (context.isAdmin()) {
          <form
            [formGroup]="outcomeForm"
            #outcomeFormDir="ngForm"
            (ngSubmit)="addOutcome(outcomeFormDir)"
            class="stack"
          >
            <h3>{{ 'protocol.outcomes.add' | transloco }}</h3>
            <mat-form-field>
              <mat-label>{{ 'protocol.outcomes.name' | transloco }}</mat-label>
              <input matInput formControlName="name" />
            </mat-form-field>
            <mat-form-field>
              <mat-label>{{ 'protocol.outcomes.type' | transloco }}</mat-label>
              <mat-select formControlName="type">
                <mat-option value="continuous">{{
                  'protocol.outcomes.types.continuous' | transloco
                }}</mat-option>
                <mat-option value="dichotomous">{{
                  'protocol.outcomes.types.dichotomous' | transloco
                }}</mat-option>
              </mat-select>
              <mat-hint>{{ 'protocol.outcomes.typeHint' | transloco }}</mat-hint>
            </mat-form-field>
            <mat-form-field>
              <mat-label>{{ 'protocol.outcomes.timepoints' | transloco }}</mat-label>
              <input matInput formControlName="timepoints" />
              <mat-hint>{{ 'protocol.outcomes.timepointsHint' | transloco }}</mat-hint>
            </mat-form-field>
            <mat-checkbox formControlName="higherIsBetter">{{
              'protocol.outcomes.higherBetter' | transloco
            }}</mat-checkbox>
            <mat-checkbox formControlName="isPrimary">{{
              'protocol.outcomes.primary' | transloco
            }}</mat-checkbox>
            <div class="actions">
              <button mat-flat-button type="submit" [disabled]="busy()">
                {{ 'protocol.outcomes.add' | transloco }}
              </button>
            </div>
          </form>
        }
      </mat-card-content>
    </mat-card>

    <mat-card class="block">
      <mat-card-header>
        <mat-card-title>
          <h2>
            {{ 'protocol.groups.title' | transloco }}
            <span class="term" tabindex="0" [matTooltip]="'glossary.comparisonGroup' | transloco"
              >?</span
            >
          </h2>
        </mat-card-title>
      </mat-card-header>
      <mat-card-content>
        @if (groups().length === 0) {
          <p class="empty">{{ 'protocol.groups.empty' | transloco }}</p>
        }
        <ul class="item-list">
          @for (group of groups(); track group.id) {
            <li>
              <div>
                <strong>{{ group.label }}</strong>
                @if (group.rule_description) {
                  <div class="muted">{{ group.rule_description }}</div>
                }
              </div>
              @if (context.isAdmin()) {
                <button mat-button type="button" (click)="removeGroup(group)">
                  {{ 'common.delete' | transloco }}
                </button>
              }
            </li>
          }
        </ul>
        @if (context.isAdmin()) {
          <form
            [formGroup]="groupForm"
            #groupFormDir="ngForm"
            (ngSubmit)="addGroup(groupFormDir)"
            class="stack"
          >
            <h3>{{ 'protocol.groups.add' | transloco }}</h3>
            <mat-form-field>
              <mat-label>{{ 'protocol.groups.label' | transloco }}</mat-label>
              <input matInput formControlName="label" />
              <mat-hint>{{ 'protocol.groups.labelHint' | transloco }}</mat-hint>
            </mat-form-field>
            <mat-form-field>
              <mat-label>{{ 'protocol.groups.rule' | transloco }}</mat-label>
              <textarea matInput formControlName="rule" rows="2"></textarea>
              <mat-hint>{{ 'protocol.groups.ruleHint' | transloco }}</mat-hint>
            </mat-form-field>
            <div class="actions">
              <button mat-flat-button type="submit" [disabled]="busy()">
                {{ 'protocol.groups.add' | transloco }}
              </button>
            </div>
          </form>
        }
      </mat-card-content>
    </mat-card>

    <rm-analysis-plan-editor [revision]="planRevision()" />

    <rm-form-editor />
  `,
})
export class ProtocolPage implements OnInit {
  private readonly api = inject(Api);
  private readonly dialog = inject(MatDialog);
  private readonly fb = inject(NonNullableFormBuilder);
  protected readonly context = inject(ProjectContext);

  protected readonly outcomes = signal<OutcomeOut[]>([]);
  protected readonly groups = signal<GroupOut[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);

  protected readonly outcomeForm = this.fb.group({
    name: ['', Validators.required],
    type: ['continuous' as 'continuous' | 'dichotomous', Validators.required],
    timepoints: [''],
    higherIsBetter: [true],
    isPrimary: [false],
  });
  protected readonly groupForm = this.fb.group({
    label: ['', Validators.required],
    rule: [''],
  });

  private projectId(): string {
    return this.context.project()?.id ?? '';
  }

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  protected readonly planRevision = signal(0);

  private async reload(): Promise<void> {
    const project_id = this.projectId();
    const [outcomes, groups] = await Promise.all([
      this.api.invoke(listOutcomes, { project_id }),
      this.api.invoke(listGroups, { project_id }),
    ]);
    this.outcomes.set(outcomes);
    this.groups.set(groups);
    // The plan lists the groups and outcomes: let it pick up the change.
    this.planRevision.update((n) => n + 1);
  }

  private async run(action: () => Promise<unknown>): Promise<boolean> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await action();
      await this.reload();
      return true;
    } catch (error) {
      this.error.set(error);
      return false;
    } finally {
      this.busy.set(false);
    }
  }

  private async confirm(data: ConfirmData): Promise<boolean> {
    const ref = this.dialog.open(ConfirmDialog, { data });
    return (await firstValueFrom(ref.afterClosed())) === true;
  }

  async setDoubleRob(enabled: boolean): Promise<void> {
    const project = this.context.project();
    if (!project) return;
    await this.run(async () => {
      const updated = await this.api.invoke(updateProject, {
        project_id: project.id,
        body: { version: project.version, double_rob: enabled },
      });
      this.context.update(updated);
    });
  }

  async setDoubleExtraction(enabled: boolean): Promise<void> {
    const project = this.context.project();
    if (!project) return;
    await this.run(async () => {
      const updated = await this.api.invoke(updateProject, {
        project_id: project.id,
        body: { version: project.version, double_extraction: enabled },
      });
      this.context.update(updated);
    });
  }

  async addOutcome(dir?: FormGroupDirective): Promise<void> {
    if (this.outcomeForm.invalid) {
      this.outcomeForm.markAllAsTouched();
      return;
    }
    const value = this.outcomeForm.getRawValue();
    const ok = await this.run(() =>
      this.api.invoke(createOutcome, {
        project_id: this.projectId(),
        body: {
          name: value.name,
          type: value.type,
          higher_is_better: value.higherIsBetter,
          is_primary: value.isPrimary,
          timepoints: value.timepoints.split(/[;,]/),
          position: this.outcomes().length,
        },
      }),
    );
    if (ok && dir) dir.resetForm();
    else if (ok) this.outcomeForm.reset();
  }

  async removeOutcome(outcome: OutcomeOut): Promise<void> {
    if (
      !(await this.confirm({ message: 'protocol.confirmDelete', params: { name: outcome.name } }))
    )
      return;
    await this.run(() =>
      this.api.invoke(deleteOutcome, { project_id: this.projectId(), outcome_id: outcome.id }),
    );
  }

  async addGroup(dir?: FormGroupDirective): Promise<void> {
    if (this.groupForm.invalid) {
      this.groupForm.markAllAsTouched();
      return;
    }
    const value = this.groupForm.getRawValue();
    const ok = await this.run(() =>
      this.api.invoke(createGroup, {
        project_id: this.projectId(),
        body: {
          label: value.label,
          rule_description: value.rule || null,
          position: this.groups().length,
        },
      }),
    );
    if (ok && dir) dir.resetForm();
    else if (ok) this.groupForm.reset();
  }

  async removeGroup(group: GroupOut): Promise<void> {
    if (!(await this.confirm({ message: 'protocol.confirmDelete', params: { name: group.label } })))
      return;
    await this.run(() =>
      this.api.invoke(deleteGroup, { project_id: this.projectId(), group_id: group.id }),
    );
  }
}
