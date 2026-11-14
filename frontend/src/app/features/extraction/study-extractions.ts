import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { Router, RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { LocalDatePipe } from '../../shared/local-date.pipe';
import { Api } from '../../core/api/api';
import { listExtractions } from '../../core/api/fn/extraction/list-extractions';
import { startExtraction } from '../../core/api/fn/extraction/start-extraction';
import { ExtractionSummary } from '../../core/api/models/extraction-summary';
import { AuthService } from '../../core/auth/auth';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

/** Extractions of a study that the current user may see, and a way to start one. */
@Component({
  selector: 'rm-study-extractions',
  imports: [LocalDatePipe, RouterLink, TranslocoPipe, MatButtonModule, FormError],
  template: `
    <ul class="item-list">
      @for (e of extractions(); track e.id) {
        <li>
          <div>
            <a [routerLink]="['/projetos', projectId(), 'extracoes', e.id]">
              {{ e.kind === 'consensus' ? ('extraction.consensus' | transloco) : e.extractor_name }}
            </a>
            <span class="badge">{{ 'extraction.status.' + e.status | transloco }}</span>
            <div class="muted">
              {{ 'extraction.updated' | transloco }} {{ e.updated_at | localDate: 'short' }}
            </div>
          </div>
        </li>
      }
    </ul>
    @if (extractions().length === 0) {
      <p class="muted">{{ 'extraction.none' | transloco }}</p>
    }
    <rm-form-error [error]="error()" />
    @if (isAdmin() && extractions().length > 0) {
      <a
        mat-stroked-button
        [routerLink]="['/projetos', projectId(), 'estudos', studyId(), 'consenso']"
      >
        {{ 'consensus.link' | transloco }}
      </a>
    }
    @if (canExtract() && !mine()) {
      <button mat-flat-button type="button" [disabled]="busy()" (click)="start()">
        {{ 'extraction.start' | transloco }}
      </button>
    }
  `,
})
export class StudyExtractions implements OnInit {
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);
  private readonly context = inject(ProjectContext);

  readonly studyId = input.required<string>();
  protected readonly extractions = signal<ExtractionSummary[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly mine = computed(() =>
    this.extractions().find(
      (e) => e.kind === 'individual' && e.extractor_id === this.auth.user()?.id,
    ),
  );
  protected readonly isAdmin = computed(() =>
    (this.context.project()?.my_roles ?? []).includes('admin'),
  );
  protected readonly canExtract = computed(() => {
    const roles = this.context.project()?.my_roles ?? [];
    return roles.includes('admin') || roles.includes('extractor');
  });

  protected projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    this.extractions.set(
      await this.api.invoke(listExtractions, {
        project_id: this.projectId(),
        study_id: this.studyId(),
      }),
    );
  }

  async start(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const extraction = await this.api.invoke(startExtraction, {
        project_id: this.projectId(),
        study_id: this.studyId(),
      });
      await this.router.navigate(['/projetos', this.projectId(), 'extracoes', extraction.id]);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
