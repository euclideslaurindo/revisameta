import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { includedToStudy } from '../../core/api/fn/screening/included-to-study';
import { includedWaitingForStudy } from '../../core/api/fn/screening/included-waiting-for-study';
import { listStudies } from '../../core/api/fn/studies/list-studies';
import { SearchReferenceOut } from '../../core/api/models/search-reference-out';
import { StudyDesign } from '../../core/api/models/study-design';
import { StudyOut } from '../../core/api/models/study-out';
import { withJsonBody } from '../../core/errors/problem';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { STUDY_DESIGNS } from '../studies/designs';

interface Draft {
  label: string;
  design: StudyDesign | null;
  studyId: string | null;
  primary: boolean;
}

/** Included articles waiting to become a study or a report of one (admin). */
@Component({
  selector: 'rm-included-studies',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <mat-card class="block">
      <mat-card-content>
        <h3>
          {{ 'screening.included.title' | transloco }}
          <span class="term" tabindex="0" [matTooltip]="'screening.included.help' | transloco"
            >?</span
          >
        </h3>
        <rm-form-error [error]="error()" />
        @if (!waiting().length) {
          <p class="muted">{{ 'screening.included.empty' | transloco }}</p>
        }
        @for (ref of waiting(); track ref.id) {
          <div class="ref">
            <strong>{{ ref.title }}</strong>
            <div class="muted">{{ ref.authors || '—' }} · {{ ref.year || '—' }}</div>
            <div class="row">
              <mat-form-field subscriptSizing="dynamic">
                <mat-label>{{ 'screening.included.label' | transloco }}</mat-label>
                <input matInput maxlength="120" [(ngModel)]="draft(ref).label" />
              </mat-form-field>
              <mat-form-field subscriptSizing="dynamic">
                <mat-label>{{ 'screening.included.design' | transloco }}</mat-label>
                <mat-select [(ngModel)]="draft(ref).design">
                  @for (d of designs; track d) {
                    <mat-option [value]="d">{{ 'designs.' + d | transloco }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
              <button
                mat-flat-button
                type="button"
                [disabled]="busy() || !draft(ref).label.trim() || !draft(ref).design"
                (click)="create(ref)"
              >
                {{ 'screening.included.create' | transloco }}
              </button>
            </div>
            @if (studies().length) {
              <div class="row">
                <mat-form-field subscriptSizing="dynamic">
                  <mat-label>{{ 'screening.included.attachTo' | transloco }}</mat-label>
                  <mat-select [(ngModel)]="draft(ref).studyId">
                    @for (s of studies(); track s.id) {
                      <mat-option [value]="s.id">{{ s.label }}</mat-option>
                    }
                  </mat-select>
                </mat-form-field>
                <mat-checkbox [(ngModel)]="draft(ref).primary">
                  {{ 'screening.included.primary' | transloco }}
                </mat-checkbox>
                <button
                  mat-stroked-button
                  type="button"
                  [disabled]="busy() || !draft(ref).studyId"
                  (click)="attach(ref)"
                >
                  {{ 'screening.included.attach' | transloco }}
                </button>
              </div>
            }
          </div>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    .ref {
      border-top: 1px solid var(--mat-sys-outline-variant, #ddd);
      padding: 8px 0;
    }
  `,
})
export class IncludedStudies implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  protected readonly designs = STUDY_DESIGNS;
  protected readonly waiting = signal<SearchReferenceOut[]>([]);
  protected readonly studies = signal<StudyOut[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  private drafts = new Map<string, Draft>();

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    await this.guard(() => this.load());
  }

  private async load(): Promise<void> {
    const [waiting, studies] = await Promise.all([
      this.api.invoke(includedWaitingForStudy, { project_id: this.projectId() }),
      this.api.invoke(listStudies, { project_id: this.projectId() }),
    ]);
    this.waiting.set(waiting);
    this.studies.set(studies);
  }

  /** Suggests "First author surname + year" as the study name. */
  protected draft(ref: SearchReferenceOut): Draft {
    let d = this.drafts.get(ref.id);
    if (!d) {
      const surname = (ref.authors ?? '').split(/[;,]/)[0].trim().split(' ')[0];
      d = {
        label: [surname, ref.year].filter((x) => x).join(' '),
        design: null,
        studyId: null,
        primary: false,
      };
      this.drafts.set(ref.id, d);
    }
    return d;
  }

  async create(ref: SearchReferenceOut): Promise<void> {
    const d = this.draft(ref);
    await this.guard(async () => {
      await this.api.invoke(includedToStudy, {
        project_id: this.projectId(),
        reference_id: ref.id,
        body: { mode: 'new', label: d.label.trim(), design: d.design },
      });
      this.drafts.delete(ref.id);
      await this.load();
    });
  }

  async attach(ref: SearchReferenceOut): Promise<void> {
    const d = this.draft(ref);
    await this.guard(async () => {
      await this.api.invoke(includedToStudy, {
        project_id: this.projectId(),
        reference_id: ref.id,
        body: { mode: 'attach', study_id: d.studyId, primary: d.primary },
      });
      this.drafts.delete(ref.id);
      await this.load();
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
