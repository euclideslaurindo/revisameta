import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';
import { toSignal } from '@angular/core/rxjs-interop';

import { Api } from '../../core/api/api';
import { pendingChecks } from '../../core/api/fn/extraction/pending-checks';
import { PendingAlert } from '../../core/api/models/pending-alert';
import { FormError } from '../../shared/form-error';
import { displayParams } from '../../shared/numbers';
import { ProjectContext } from '../project/project-context';

/** "Pendências de conferência": open alerts in the extractions the user may see. */
@Component({
  selector: 'rm-pending-page',
  imports: [RouterLink, TranslocoPipe, FormError],
  template: `
    <p class="muted">{{ 'pending.intro' | transloco }}</p>
    <rm-form-error [error]="error()" />
    @if (loaded() && alerts().length === 0) {
      <p class="empty">{{ 'pending.empty' | transloco }}</p>
    }
    <ul class="item-list">
      @for (a of alerts(); track a.id) {
        <li>
          <div>
            <a [routerLink]="['/projetos', projectId(), 'extracoes', a.extraction_id]">{{
              a.study_label
            }}</a>
            <span class="badge" [class.badge-block]="a.severity === 'block'">{{
              'extraction.alertSeverity.' + a.severity | transloco
            }}</span>
            <div>{{ a.code | transloco: params(a.params) }}</div>
          </div>
        </li>
      }
    </ul>
  `,
})
export class PendingPage implements OnInit {
  private readonly api = inject(Api);
  private readonly lang = toSignal(inject(TranslocoService).langChanges$, {
    initialValue: 'pt-BR',
  });

  protected params(params: Record<string, unknown> | null | undefined): Record<string, unknown> {
    return displayParams(params, this.lang());
  }
  private readonly context = inject(ProjectContext);

  protected readonly alerts = signal<PendingAlert[]>([]);
  protected readonly loaded = signal(false);
  protected readonly error = signal<unknown>(null);

  protected projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    try {
      this.alerts.set(await this.api.invoke(pendingChecks, { project_id: this.projectId() }));
    } catch (error) {
      this.error.set(error);
    } finally {
      this.loaded.set(true);
    }
  }
}
