import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { getForm } from '../../core/api/fn/extraction/get-form';
import { updateForm } from '../../core/api/fn/extraction/update-form';
import { FormField } from '../../core/api/models/form-field';
import { FormOut } from '../../core/api/models/form-out';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

type FieldType = FormField['type'];

/** Built-in fields of the default form (docs/modulos.md 7.5): they can be removed and added back. */
const BUILT_IN: { key: string; type: FieldType }[] = [
  { key: 'country', type: 'text' },
  { key: 'period', type: 'text' },
  { key: 'centers', type: 'number' },
  { key: 'n_total', type: 'number' },
  { key: 'eligibility', type: 'textarea' },
  { key: 'cutoff_used', type: 'text' },
  { key: 'surgery_type', type: 'text' },
  { key: 'follow_up', type: 'text' },
  { key: 'funding', type: 'text' },
  { key: 'conflict_of_interest', type: 'text' },
];
const TYPES: FieldType[] = ['text', 'textarea', 'number', 'select', 'date'];

/** snake_case key from a label, unique among the fields ("Tipo de anestesia" → tipo_de_anestesia). */
export function keyFor(label: string, taken: Set<string>): string {
  const base =
    label
      .normalize('NFKD')
      .replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 36) || 'campo';
  const start = /^[a-z]/.test(base) ? base : `campo_${base}`.slice(0, 36);
  let key = start;
  for (let i = 2; taken.has(key); i++) key = `${start}_${i}`;
  return key;
}

/**
 * Editor of the characteristics form (versioned: saving creates a new version and
 * extractions on the old one are flagged for review).
 */
@Component({
  selector: 'rm-form-editor',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <mat-card class="block">
      <mat-card-header>
        <mat-card-title>
          <h3>
            {{ 'formEditor.title' | transloco }}
            <span class="term" tabindex="0" [matTooltip]="'formEditor.help' | transloco">?</span>
          </h3>
        </mat-card-title>
      </mat-card-header>
      <mat-card-content>
        @if (form(); as f) {
          <p class="muted">{{ 'formEditor.version' | transloco: { version: f.form_version } }}</p>
          <ul class="item-list">
            @for (field of fields(); track field.key; let i = $index; let last = $last) {
              <li>
                <div>
                  {{ field.label_key ? (field.label_key | transloco) : field.label }}
                  <span class="badge">{{ 'formEditor.types.' + field.type | transloco }}</span>
                  @if (field.options?.length) {
                    <div class="muted">{{ field.options!.join(' · ') }}</div>
                  }
                </div>
                @if (isAdmin()) {
                  <div class="actions">
                    <button
                      mat-button
                      type="button"
                      [disabled]="i === 0"
                      (click)="move(i, -1)"
                      [attr.aria-label]="'formEditor.up' | transloco"
                    >
                      ↑
                    </button>
                    <button
                      mat-button
                      type="button"
                      [disabled]="last"
                      (click)="move(i, 1)"
                      [attr.aria-label]="'formEditor.down' | transloco"
                    >
                      ↓
                    </button>
                    <button mat-button type="button" (click)="remove(i)">
                      {{ 'common.delete' | transloco }}
                    </button>
                  </div>
                }
              </li>
            }
          </ul>

          @if (isAdmin()) {
            @if (removedBuiltIns().length) {
              <p class="muted">{{ 'formEditor.addBack' | transloco }}</p>
              <div class="actions">
                @for (b of removedBuiltIns(); track b.key) {
                  <button mat-stroked-button type="button" (click)="addBack(b.key, b.type)">
                    + {{ 'extraction.fields.' + b.key | transloco }}
                  </button>
                }
              </div>
            }

            <h4>{{ 'formEditor.newField' | transloco }}</h4>
            <div class="row">
              <mat-form-field subscriptSizing="dynamic" class="wide">
                <mat-label>{{ 'formEditor.label' | transloco }}</mat-label>
                <input matInput [(ngModel)]="newLabel" maxlength="200" />
              </mat-form-field>
              <mat-form-field subscriptSizing="dynamic">
                <mat-label>{{ 'formEditor.type' | transloco }}</mat-label>
                <mat-select [(ngModel)]="newType">
                  @for (t of types; track t) {
                    <mat-option [value]="t">{{ 'formEditor.types.' + t | transloco }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
            </div>
            @if (newType === 'select') {
              <mat-form-field subscriptSizing="dynamic" class="wide">
                <mat-label>{{ 'formEditor.options' | transloco }}</mat-label>
                <input matInput [(ngModel)]="newOptions" />
                <mat-hint>{{ 'formEditor.optionsHint' | transloco }}</mat-hint>
              </mat-form-field>
            }
            <mat-form-field subscriptSizing="dynamic" class="wide">
              <mat-label>{{ 'formEditor.fieldHelp' | transloco }}</mat-label>
              <input matInput [(ngModel)]="newHelp" maxlength="500" />
            </mat-form-field>
            @if (problem(); as key) {
              <div class="notice notice-error" role="alert">{{ key | transloco }}</div>
            }
            <div class="actions">
              <button mat-stroked-button type="button" (click)="add()">
                {{ 'formEditor.add' | transloco }}
              </button>
            </div>

            @if (dirty()) {
              <p class="notice">
                {{ 'formEditor.saveHint' | transloco: { next: f.form_version + 1 } }}
              </p>
            }
            <rm-form-error [error]="error()" />
            <div class="actions">
              <button
                mat-flat-button
                type="button"
                [disabled]="busy() || !dirty()"
                (click)="save()"
              >
                {{ 'formEditor.save' | transloco }}
              </button>
              @if (dirty()) {
                <button mat-button type="button" (click)="discard()">
                  {{ 'common.cancel' | transloco }}
                </button>
              }
            </div>
          }
        }
      </mat-card-content>
    </mat-card>
  `,
})
export class FormEditor implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  protected readonly form = signal<FormOut | null>(null);
  protected readonly fields = signal<FormField[]>([]);
  protected readonly dirty = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly problem = signal<string | null>(null);
  protected readonly types = TYPES;
  protected readonly isAdmin = computed(() => this.context.isAdmin());
  protected readonly removedBuiltIns = computed(() => {
    const keys = new Set(this.fields().map((f) => f.key));
    return BUILT_IN.filter((b) => !keys.has(b.key));
  });
  protected newLabel = '';
  protected newType: FieldType = 'text';
  protected newOptions = '';
  protected newHelp = '';

  async ngOnInit(): Promise<void> {
    try {
      this.reset(await this.api.invoke(getForm, { project_id: this.context.project()!.id }));
    } catch (error) {
      this.error.set(error);
    }
  }

  private reset(form: FormOut): void {
    this.form.set(form);
    this.fields.set(form.schema.fields.map((f) => ({ ...f })));
    this.dirty.set(false);
  }

  private edit(fields: FormField[]): void {
    this.fields.set(fields);
    this.dirty.set(true);
  }

  protected move(index: number, delta: number): void {
    const fields = [...this.fields()];
    const [field] = fields.splice(index, 1);
    fields.splice(index + delta, 0, field);
    this.edit(fields);
  }

  protected remove(index: number): void {
    this.edit(this.fields().filter((_, i) => i !== index));
  }

  protected addBack(key: string, type: FieldType): void {
    this.edit([...this.fields(), { key, type, label_key: `extraction.fields.${key}` }]);
  }

  protected add(): void {
    const label = this.newLabel.trim();
    if (!label) return this.problem.set('formEditor.errors.label');
    const options = this.newOptions
      .split(';')
      .map((o) => o.trim())
      .filter(Boolean);
    if (this.newType === 'select' && options.length < 2)
      return this.problem.set('formEditor.errors.options');
    this.problem.set(null);
    const key = keyFor(label, new Set(this.fields().map((f) => f.key)));
    const field: FormField = { key, type: this.newType, label, help: this.newHelp.trim() || null };
    if (this.newType === 'select') field.options = options;
    this.edit([...this.fields(), field]);
    this.newLabel = '';
    this.newOptions = '';
    this.newHelp = '';
    this.newType = 'text';
  }

  protected discard(): void {
    const form = this.form();
    if (form) this.reset(form);
  }

  async save(): Promise<void> {
    const form = this.form();
    if (!form) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      this.reset(
        await this.api.invoke(updateForm, {
          project_id: this.context.project()!.id,
          body: { version: form.version, schema: { fields: this.fields() } },
        }),
      );
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
