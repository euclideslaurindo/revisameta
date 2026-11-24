import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { aiSettings } from '../../core/api/fn/ai/ai-settings';
import { updateAiSettings } from '../../core/api/fn/ai/update-ai-settings';
import { AiSettingsOut } from '../../core/api/models/ai-settings-out';
import { withJsonBody } from '../../core/errors/problem';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from './project-context';

interface Notice {
  title: string;
  paragraphs: string[];
  accept: string;
}

/** Project settings. For now: the AI, off by default, on only with the notice accepted. */
@Component({
  selector: 'rm-settings-page',
  imports: [
    DatePipe,
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <mat-card class="block">
      <mat-card-content>
        <h2>
          {{ 'settings.ai.title' | transloco }}
          <span class="term" tabindex="0" [matTooltip]="'settings.ai.help' | transloco">?</span>
        </h2>
        <rm-form-error [error]="error()" />
        @if (data(); as d) {
          <p>
            <strong>{{ (d.enabled ? 'settings.ai.on' : 'settings.ai.off') | transloco }}</strong>
            @if (d.enabled && d.accepted_at) {
              ·
              {{
                'settings.ai.acceptedBy'
                  | transloco: { name: d.accepted_by_name, date: (d.accepted_at | date: 'short') }
              }}
            }
          </p>
          @if (!d.server_configured) {
            <p class="warning" role="status">{{ 'settings.ai.notConfigured' | transloco }}</p>
          }
          @if (d.accepted_version && d.accepted_version !== d.notice_version) {
            <p class="warning" role="status">{{ 'settings.ai.newNotice' | transloco }}</p>
          }
          @for (key of disabledKeys(); track key) {
            <p class="warning" role="status">
              {{
                'settings.ai.lowAccuracy' | transloco: { fn: ('settings.ai.fn.' + key | transloco) }
              }}
            </p>
          }

          @if (notice(); as n) {
            <section class="notice-box" [attr.aria-label]="n.title">
              <h3>{{ n.title }}</h3>
              @for (p of n.paragraphs; track $index) {
                <p>{{ p }}</p>
              }
            </section>
          }

          @if (isAdmin()) {
            <h3>{{ 'settings.ai.functions' | transloco }}</h3>
            @for (fn of allFunctions; track fn) {
              <div>
                <mat-checkbox [checked]="chosen().has(fn)" (change)="toggle(fn, $event.checked)">
                  {{ 'settings.ai.fn.' + fn | transloco }}
                </mat-checkbox>
              </div>
            }
            @if (!d.enabled) {
              <mat-checkbox [(ngModel)]="accepted">{{ notice()?.accept }}</mat-checkbox>
              <div class="actions">
                <button
                  mat-flat-button
                  type="button"
                  [disabled]="busy() || !accepted"
                  (click)="save(true)"
                >
                  {{ 'settings.ai.turnOn' | transloco }}
                </button>
              </div>
            } @else {
              <div class="actions">
                <button mat-stroked-button type="button" [disabled]="busy()" (click)="save(true)">
                  {{ 'settings.ai.saveFunctions' | transloco }}
                </button>
                <button mat-stroked-button type="button" [disabled]="busy()" (click)="save(false)">
                  {{ 'settings.ai.turnOff' | transloco }}
                </button>
              </div>
            }
          } @else {
            <p class="muted">{{ 'settings.ai.adminOnly' | transloco }}</p>
          }
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    .notice-box {
      border: 1px solid var(--mat-sys-outline-variant);
      border-radius: 8px;
      padding: 8px 16px;
      margin: 12px 0;
    }
  `,
})
export class SettingsPage implements OnInit {
  private readonly api = inject(Api);
  private readonly transloco = inject(TranslocoService);
  private readonly context = inject(ProjectContext);

  protected readonly allFunctions = ['tutor', 'locate'] as const;
  protected readonly data = signal<AiSettingsOut | null>(null);
  protected readonly chosen = signal(new Set<string>());
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected accepted = false;
  protected readonly isAdmin = computed(
    () => this.context.project()?.my_roles?.includes('admin') ?? false,
  );
  protected readonly notice = computed(() => {
    const d = this.data();
    if (!d) return null;
    const lang = this.transloco.getActiveLang().startsWith('en') ? 'en' : 'pt-BR';
    return d.notice[lang] as unknown as Notice;
  });
  protected readonly disabledKeys = computed(() =>
    Object.keys(this.data()?.disabled_functions ?? {}),
  );

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    await this.guard(async () =>
      this.set(await this.api.invoke(aiSettings, { project_id: this.projectId() })),
    );
  }

  private set(d: AiSettingsOut): void {
    this.data.set(d);
    this.chosen.set(new Set(d.functions));
    this.accepted = false;
  }

  protected toggle(fn: string, on: boolean): void {
    const next = new Set(this.chosen());
    if (on) next.add(fn);
    else next.delete(fn);
    this.chosen.set(next);
  }

  async save(enabled: boolean): Promise<void> {
    const d = this.data();
    if (!d) return;
    await this.guard(async () => {
      const out = await this.api.invoke(updateAiSettings, {
        project_id: this.projectId(),
        body: {
          enabled,
          functions: [...this.chosen()] as ('tutor' | 'locate')[],
          accept_notice_version: enabled && !d.enabled ? d.notice_version : null,
          version: d.version ?? null,
        },
      });
      this.set(out);
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
