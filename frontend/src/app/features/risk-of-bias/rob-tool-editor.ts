import { Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { setRobToolStructure } from '../../core/api/fn/risk-of-bias/set-rob-tool-structure';
import { setRobToolTexts } from '../../core/api/fn/risk-of-bias/set-rob-tool-texts';
import { ToolOut } from '../../core/api/models/tool-out';
import { FormError } from '../../shared/form-error';

interface TemplateQuestion {
  key: string;
  level: 'study' | 'outcome' | 'result';
}
interface TemplateDomain {
  key: string;
  name: Record<string, string>;
  questions: TemplateQuestion[];
}

/** Localized name of a template element ({"pt-BR": ..., "en": ...}). */
export function localized(name: Record<string, string> | undefined, lang: string): string {
  if (!name) return '';
  return name[lang] ?? name['pt-BR'] ?? Object.values(name)[0] ?? '';
}

/**
 * Official wording of an instrument, pasted by the admin from the official source
 * (the system ships only the structure). The generic instrument also gets its domains here.
 */
@Component({
  selector: 'rm-rob-tool-editor',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    FormError,
  ],
  template: `
    @if (tool().family === 'generic') {
      <h4>{{ 'rob.generic.title' | transloco }}</h4>
      <p class="muted">{{ 'rob.generic.hint' | transloco }}</p>
      @for (d of genericDomains; track $index) {
        <div class="row">
          <mat-form-field subscriptSizing="dynamic" class="wide">
            <mat-label>{{ 'rob.generic.domain' | transloco: { n: $index + 1 } }}</mat-label>
            <input matInput [(ngModel)]="d.name" maxlength="200" />
          </mat-form-field>
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'rob.generic.questions' | transloco }}</mat-label>
            <input matInput type="number" min="1" max="40" [(ngModel)]="d.questions" />
          </mat-form-field>
          <button mat-button type="button" (click)="genericDomains.splice($index, 1)">
            {{ 'common.delete' | transloco }}
          </button>
        </div>
      }
      <div class="actions">
        <button
          mat-stroked-button
          type="button"
          (click)="genericDomains.push({ name: '', questions: 1 })"
        >
          {{ 'rob.generic.addDomain' | transloco }}
        </button>
        <button mat-flat-button type="button" [disabled]="busy()" (click)="saveStructure()">
          {{ 'rob.generic.save' | transloco }}
        </button>
      </div>
    }

    <h4>{{ 'rob.texts.title' | transloco }}</h4>
    <p class="muted">{{ 'rob.texts.hint' | transloco }}</p>
    @for (d of domains(); track d.key) {
      <h5>{{ localized(d.name) }}</h5>
      @for (q of d.questions; track q.key) {
        <mat-form-field subscriptSizing="dynamic" class="wide block-field">
          <mat-label>
            {{ 'rob.texts.question' | transloco: { n: q.key } }} ·
            {{ 'rob.level.' + q.level | transloco }}
          </mat-label>
          <textarea
            matInput
            rows="2"
            [(ngModel)]="texts[d.key + '.' + q.key]"
            maxlength="4000"
          ></textarea>
        </mat-form-field>
      }
    }
    <rm-form-error [error]="error()" />
    <div class="actions">
      <button mat-flat-button type="button" [disabled]="busy()" (click)="saveTexts()">
        {{ 'rob.texts.save' | transloco }}
      </button>
      <button mat-button type="button" (click)="closed.emit()">
        {{ 'common.cancel' | transloco }}
      </button>
    </div>
  `,
})
export class RobToolEditor implements OnInit {
  private readonly api = inject(Api);
  private readonly lang = toSignal(inject(TranslocoService).langChanges$, {
    initialValue: 'pt-BR',
  });

  readonly projectId = input.required<string>();
  readonly tool = input.required<ToolOut>();
  readonly saved = output<ToolOut>();
  readonly closed = output<void>();

  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly domains = computed(
    () => (this.tool().structure['domains'] ?? []) as TemplateDomain[],
  );
  protected texts: Record<string, string> = {};
  protected genericDomains: { name: string; questions: number }[] = [];

  ngOnInit(): void {
    this.texts = { ...this.tool().texts };
    this.genericDomains = this.domains().map((d) => ({
      name: localized(d.name, 'pt-BR'),
      questions: d.questions.length,
    }));
    if (this.tool().family === 'generic' && this.genericDomains.length === 0) {
      this.genericDomains.push({ name: '', questions: 1 });
    }
  }

  protected localized(name: Record<string, string>): string {
    return localized(name, this.lang());
  }

  private async run(action: () => Promise<ToolOut>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const tool = await action();
      this.saved.emit(tool);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }

  async saveTexts(): Promise<void> {
    const texts: Record<string, string | null> = {};
    for (const d of this.domains()) {
      for (const q of d.questions) {
        const key = `${d.key}.${q.key}`;
        texts[key] = this.texts[key]?.trim() || null;
      }
    }
    await this.run(() =>
      this.api.invoke(setRobToolTexts, {
        project_id: this.projectId(),
        tool_id: this.tool().id,
        body: { version: this.tool().version, texts },
      }),
    );
  }

  async saveStructure(): Promise<void> {
    await this.run(() =>
      this.api.invoke(setRobToolStructure, {
        project_id: this.projectId(),
        tool_id: this.tool().id,
        body: {
          version: this.tool().version,
          domains: this.genericDomains.map((d) => ({
            name: d.name,
            questions: Number(d.questions),
          })),
        },
      }),
    );
  }
}
