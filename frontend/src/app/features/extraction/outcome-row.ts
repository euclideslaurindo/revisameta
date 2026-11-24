import {
  Component,
  OnDestroy,
  OnInit,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { HttpErrorResponse } from '@angular/common/http';

import { addOutcomeData } from '../../core/api/fn/extraction/add-outcome-data';
import { getExtraction } from '../../core/api/fn/extraction/get-extraction';
import { updateOutcomeData } from '../../core/api/fn/extraction/update-outcome-data';
import { AlertOut } from '../../core/api/models/alert-out';
import { AnnotationOut } from '../../core/api/models/annotation-out';
import { DispersionType } from '../../core/api/models/dispersion-type';
import { EffectReportedInput } from '../../core/api/models/effect-reported-input';
import { OutcomeDataFields } from '../../core/api/models/outcome-data-fields';
import { OutcomeDataOut } from '../../core/api/models/outcome-data-out';
import { isValidNumberText, parseDecimal, parseInteger } from '../../shared/numbers';
import { AlertMessage } from './alert-message';
import { AutosaveState } from './autosave';

const DECIMALS = [
  'mean',
  'sd',
  'se',
  'ci_low',
  'ci_high',
  'median',
  'q1',
  'q3',
  'min',
  'max',
  't_stat',
  'p_value',
] as const;
const EFFECT_NUMBERS = ['estimate', 'ci_low', 'ci_high', 'se'] as const;
type EffectNumber = (typeof EFFECT_NUMBERS)[number];
const MEASURES: EffectReportedInput['measure'][] = ['OR', 'RR', 'HR', 'MD', 'SMD', 'other'];
const INTEGERS = ['n', 'events', 'total'] as const;
type NumberKey = (typeof DECIMALS)[number] | (typeof INTEGERS)[number];

/** Which inputs each dispersion type shows (bloco A item 1: the type is required). */
const DISPERSION_INPUTS: Record<DispersionType, NumberKey[]> = {
  sd: ['sd'],
  se: ['se'],
  ci95: ['ci_low', 'ci_high'],
  iqr: ['median', 'q1', 'q3'],
  range: ['median', 'min', 'max'],
  not_reported: [],
};
const DISPERSIONS = Object.keys(DISPERSION_INPUTS) as DispersionType[];
const SAVE_DELAY_MS = 800;

/** The numbers of one outcome, for one group, at one time point. Saves itself. */
@Component({
  selector: 'rm-outcome-row',
  imports: [
    AlertMessage,
    FormsModule,
    MatButtonModule,
    TranslocoPipe,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
  ],
  template: `
    <div class="outcome-row" [class.readonly]="!editable()">
      <div class="row-head">
        <strong>{{ armLabel() }}</strong>
        <span class="muted">· {{ timepoint() }}</span>
      </div>
      @if (dichotomous()) {
        <div class="row">
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'extraction.data.events' | transloco }}</mat-label>
            <input
              matInput
              [(ngModel)]="text.events"
              (ngModelChange)="changed()"
              [disabled]="!editable()"
              inputmode="numeric"
            />
          </mat-form-field>
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'extraction.data.total' | transloco }}</mat-label>
            <input
              matInput
              [(ngModel)]="text.total"
              (ngModelChange)="changed()"
              [disabled]="!editable()"
              inputmode="numeric"
            />
          </mat-form-field>
        </div>
      } @else {
        <div class="row">
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'extraction.data.valueType' | transloco }}</mat-label>
            <mat-select
              [(ngModel)]="valueType"
              (ngModelChange)="changed()"
              [disabled]="!editable()"
            >
              <mat-option value="final">{{ 'extraction.data.final' | transloco }}</mat-option>
              <mat-option value="change">{{ 'extraction.data.change' | transloco }}</mat-option>
            </mat-select>
          </mat-form-field>
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>n</mat-label>
            <input
              matInput
              [(ngModel)]="text.n"
              (ngModelChange)="changed()"
              [disabled]="!editable()"
              inputmode="numeric"
            />
          </mat-form-field>
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'extraction.data.mean' | transloco }}</mat-label>
            <input
              matInput
              [(ngModel)]="text.mean"
              (ngModelChange)="changed()"
              [disabled]="!editable()"
              inputmode="decimal"
            />
          </mat-form-field>
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>
              {{ 'extraction.data.dispersionType' | transloco }}
            </mat-label>
            <mat-select
              [(ngModel)]="dispersionType"
              (ngModelChange)="changed()"
              [disabled]="!editable()"
            >
              @for (d of dispersions; track d) {
                <mat-option [value]="d">{{ 'extraction.dispersion.' + d | transloco }}</mat-option>
              }
            </mat-select>
            <mat-hint>{{ 'extraction.data.dispersionHint' | transloco }}</mat-hint>
          </mat-form-field>
        </div>
        @if (dispersionType) {
          <div class="row">
            @for (key of dispersionInputs(); track key) {
              <mat-form-field subscriptSizing="dynamic">
                <mat-label>{{ 'extraction.data.fields.' + key | transloco }}</mat-label>
                <input
                  matInput
                  [(ngModel)]="text[key]"
                  (ngModelChange)="changed()"
                  [disabled]="!editable()"
                  inputmode="decimal"
                />
              </mat-form-field>
            }
            @if (dispersionType !== 'not_reported') {
              <mat-form-field subscriptSizing="dynamic" class="wide">
                <mat-label>{{ 'extraction.data.dispersionSource' | transloco }}</mat-label>
                <input
                  matInput
                  [(ngModel)]="dispersionSource"
                  (ngModelChange)="changed()"
                  [disabled]="!editable()"
                />
                <mat-hint>{{ 'extraction.data.dispersionSourceHint' | transloco }}</mat-hint>
              </mat-form-field>
            }
          </div>
        }
      }
      <button mat-button type="button" class="extra-toggle" (click)="showExtra.set(!showExtra())">
        {{
          (showExtra() ? 'extraction.data.extra.hide' : 'extraction.data.extra.show') | transloco
        }}
      </button>
      @if (showExtra()) {
        <div class="extra">
          <p class="muted">{{ 'extraction.data.extra.hint' | transloco }}</p>
          <div class="row">
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'extraction.data.extra.measure' | transloco }}</mat-label>
              <mat-select
                [(ngModel)]="effectMeasure"
                (ngModelChange)="changed()"
                [disabled]="!editable()"
              >
                <mat-option [value]="null">{{
                  'extraction.data.extra.noEffect' | transloco
                }}</mat-option>
                @for (m of measures; track m) {
                  <mat-option [value]="m">{{
                    'extraction.data.extra.measures.' + m | transloco
                  }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
            @if (effectMeasure) {
              @for (key of effectNumbers; track key) {
                <mat-form-field subscriptSizing="dynamic">
                  <mat-label>{{ 'extraction.data.extra.' + key | transloco }}</mat-label>
                  <input
                    matInput
                    [(ngModel)]="effect[key]"
                    (ngModelChange)="changed()"
                    [disabled]="!editable()"
                    inputmode="decimal"
                  />
                </mat-form-field>
              }
            }
          </div>
          <div class="row">
            <mat-checkbox
              [(ngModel)]="adjusted"
              (ngModelChange)="changed()"
              [disabled]="!editable()"
            >
              {{ 'extraction.data.extra.adjusted' | transloco }}
            </mat-checkbox>
            @if (adjusted) {
              <mat-form-field subscriptSizing="dynamic" class="wide">
                <mat-label>{{ 'extraction.data.extra.adjustedFor' | transloco }}</mat-label>
                <input
                  matInput
                  [(ngModel)]="adjustedFor"
                  (ngModelChange)="changed()"
                  [disabled]="!editable()"
                />
              </mat-form-field>
            }
          </div>
          <div class="row">
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'extraction.data.extra.t_stat' | transloco }}</mat-label>
              <input
                matInput
                [(ngModel)]="text.t_stat"
                (ngModelChange)="changed()"
                [disabled]="!editable()"
                inputmode="decimal"
              />
            </mat-form-field>
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'extraction.data.extra.p_value' | transloco }}</mat-label>
              <input
                matInput
                [(ngModel)]="text.p_value"
                (ngModelChange)="changed()"
                [disabled]="!editable()"
                inputmode="decimal"
              />
            </mat-form-field>
          </div>
        </div>
      }
      <div class="row">
        <mat-form-field subscriptSizing="dynamic">
          <mat-label>{{ 'extraction.data.source' | transloco }}</mat-label>
          <mat-select [(ngModel)]="source" (ngModelChange)="changed()" [disabled]="!editable()">
            @for (s of sources; track s) {
              <mat-option [value]="s">{{
                'extraction.data.sourceName.' + s | transloco
              }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-form-field subscriptSizing="dynamic" class="wide">
          <mat-label>{{ 'extraction.data.sourceLocation' | transloco }}</mat-label>
          <input
            matInput
            [(ngModel)]="sourceLocation"
            (ngModelChange)="changed()"
            [disabled]="!editable()"
          />
        </mat-form-field>
        <mat-form-field subscriptSizing="dynamic" class="wide">
          <mat-label>{{ 'extraction.data.annotation' | transloco }}</mat-label>
          <mat-select
            [(ngModel)]="annotationId"
            (ngModelChange)="changed()"
            [disabled]="!editable()"
          >
            <mat-option [value]="null">{{ 'extraction.data.noAnnotation' | transloco }}</mat-option>
            @for (a of annotations(); track a.id) {
              <mat-option [value]="a.id"
                >{{ 'pdfs.page' | transloco: { page: a.page } }} · {{ a.quote }}</mat-option
              >
            }
          </mat-select>
        </mat-form-field>
      </div>
      @if (problem(); as key) {
        <div class="notice notice-error" role="alert">{{ key | transloco }}</div>
      }
      @for (alert of alerts(); track alert.id) {
        <rm-alert-message [projectId]="projectId()" [alert]="alert" [canJustify]="editable()" />
      }
    </div>
  `,
})
export class OutcomeRow implements OnInit, OnDestroy {
  private readonly api = inject(Api);
  private readonly autosave = inject(AutosaveState);

  readonly projectId = input.required<string>();
  readonly extractionId = input.required<string>();
  readonly outcomeId = input.required<string>();
  readonly dichotomous = input(false);
  readonly armId = input.required<string>();
  readonly armLabel = input.required<string>();
  readonly timepoint = input.required<string>();
  readonly row = input<OutcomeDataOut | null>(null);
  readonly annotations = input<AnnotationOut[]>([]);
  readonly editable = input(true);
  readonly alerts = input<AlertOut[]>([]);
  readonly saved = output<OutcomeDataOut>();

  protected readonly dispersions = DISPERSIONS;
  protected readonly problem = signal<string | null>(null);
  protected text: Record<NumberKey, string> = Object.fromEntries(
    [...DECIMALS, ...INTEGERS].map((k) => [k, '']),
  ) as Record<NumberKey, string>;
  protected valueType: 'final' | 'change' = 'final';
  protected dispersionType: DispersionType | null = null;
  protected dispersionSource = '';
  protected sourceLocation = '';
  protected source: 'article' | 'author' | 'digitizer' = 'article';
  protected readonly sources = ['article', 'author', 'digitizer'] as const;
  protected annotationId: string | null = null;
  protected readonly measures = MEASURES;
  protected readonly effectNumbers = EFFECT_NUMBERS;
  protected effectMeasure: EffectReportedInput['measure'] | null = null;
  protected effect: Record<EffectNumber, string> = {
    estimate: '',
    ci_low: '',
    ci_high: '',
    se: '',
  };
  protected adjusted = false;
  protected adjustedFor = '';
  /** Optional data (effect computed by the article, p value, t): open when already filled. */
  protected readonly showExtra = signal(false);
  protected readonly dispersionInputs = computed(
    () => DISPERSION_INPUTS[this.dispersionTypeSignal() ?? 'not_reported'],
  );
  private readonly dispersionTypeSignal = signal<DispersionType | null>(null);
  private current: OutcomeDataOut | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  // Saves run one after the other, so a slow first save never creates a duplicate row.
  private queue: Promise<void> = Promise.resolve();

  constructor() {
    // The server may bump the row (e.g. direction confirmed): keep its newest version
    // without touching what the user is typing.
    effect(() => {
      const row = this.row();
      if (row && this.current && row.id === this.current.id && row.version > this.current.version) {
        this.current = row;
      }
    });
  }

  ngOnInit(): void {
    const row = this.row();
    this.current = row;
    if (!row) return;
    for (const key of [...DECIMALS, ...INTEGERS]) {
      const value = row[key];
      this.text[key] = value === null || value === undefined ? '' : String(value).replace('.', ',');
    }
    this.valueType = row.value_type;
    this.dispersionType = row.dispersion_type ?? null;
    this.dispersionTypeSignal.set(this.dispersionType);
    this.dispersionSource = row.dispersion_source ?? '';
    this.sourceLocation = row.source_location ?? '';
    this.source = row.source === 'author' || row.source === 'digitizer' ? row.source : 'article';
    this.annotationId = row.annotation_id ?? null;
    const effect = row.effect_reported;
    if (effect) {
      this.effectMeasure = effect.measure as EffectReportedInput['measure'];
      for (const key of EFFECT_NUMBERS) {
        const value = effect[key];
        this.effect[key] =
          value === null || value === undefined ? '' : String(value).replace('.', ',');
      }
    }
    this.adjusted = row.adjusted ?? false;
    this.adjustedFor = row.adjusted_for ?? '';
    this.showExtra.set(!!effect || this.adjusted || row.t_stat != null || row.p_value != null);
  }

  ngOnDestroy(): void {
    if (this.timer) clearTimeout(this.timer);
  }

  protected changed(): void {
    this.dispersionTypeSignal.set(this.dispersionType);
    this.autosave.markDirty();
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.queue = this.queue.then(() => this.save());
    }, SAVE_DELAY_MS);
  }

  private values(): OutcomeDataFields | null {
    for (const key of DECIMALS) {
      if (!isValidNumberText(this.text[key])) return this.fail('extraction.data.errors.notANumber');
    }
    for (const key of INTEGERS) {
      if (!isValidNumberText(this.text[key], true))
        return this.fail('extraction.data.errors.notAnInteger');
    }
    for (const key of EFFECT_NUMBERS) {
      if (!isValidNumberText(this.effect[key]))
        return this.fail('extraction.data.errors.notANumber');
    }
    // An effect needs both its measure and its estimate.
    const estimate = parseDecimal(this.effect.estimate);
    if (this.effectMeasure && estimate === null)
      return this.fail('extraction.data.errors.effectIncomplete');
    const allowed = new Set<NumberKey>([
      'n',
      'mean',
      't_stat',
      'p_value',
      'events',
      'total',
      ...DISPERSION_INPUTS[this.dispersionType ?? 'not_reported'],
    ]);
    const hasDispersionValue = (
      ['sd', 'se', 'ci_low', 'ci_high', 'q1', 'q3', 'min', 'max'] as const
    ).some((k) => this.text[k].trim() && allowed.has(k));
    if (!this.dispersionType && hasDispersionValue)
      return this.fail('extraction.data.errors.dispersionTypeRequired');
    this.problem.set(null);
    const decimal = (k: NumberKey) => (allowed.has(k) ? parseDecimal(this.text[k]) : null);
    const integer = (k: NumberKey) => (allowed.has(k) ? parseInteger(this.text[k]) : null);
    return {
      n: integer('n'),
      mean: decimal('mean'),
      dispersion_type: this.dispersionType,
      dispersion_source: this.dispersionSource || null,
      sd: decimal('sd'),
      se: decimal('se'),
      ci_low: decimal('ci_low'),
      ci_high: decimal('ci_high'),
      median: decimal('median'),
      q1: decimal('q1'),
      q3: decimal('q3'),
      min: decimal('min'),
      max: decimal('max'),
      events: integer('events'),
      total: integer('total'),
      t_stat: decimal('t_stat'),
      p_value: decimal('p_value'),
      effect_reported:
        this.effectMeasure && estimate !== null
          ? {
              measure: this.effectMeasure,
              estimate,
              ci_low: parseDecimal(this.effect.ci_low),
              ci_high: parseDecimal(this.effect.ci_high),
              se: parseDecimal(this.effect.se),
            }
          : null,
      adjusted: this.adjusted,
      adjusted_for: this.adjusted ? this.adjustedFor || null : null,
      source_location: this.sourceLocation || null,
      source: this.source,
      annotation_id: this.annotationId,
    };
  }

  private fail(key: string): null {
    this.problem.set(key);
    return null;
  }

  /** The newest copy of this row on the server (another save may have bumped it). */
  private async latest(): Promise<OutcomeDataOut | null> {
    const detail = await this.api.invoke(getExtraction, {
      project_id: this.projectId(),
      extraction_id: this.extractionId(),
    });
    return (
      detail.outcome_data.find(
        (r) =>
          r.outcome_id === this.outcomeId() &&
          r.arm_id === this.armId() &&
          r.timepoint === this.timepoint(),
      ) ?? null
    );
  }

  private send(values: OutcomeDataFields): Promise<OutcomeDataOut> {
    return this.current
      ? this.api.invoke(updateOutcomeData, {
          project_id: this.projectId(),
          row_id: this.current.id,
          body: { version: this.current.version, value_type: this.valueType, values },
        })
      : this.api.invoke(addOutcomeData, {
          project_id: this.projectId(),
          extraction_id: this.extractionId(),
          body: {
            ...values,
            arm_id: this.armId(),
            outcome_id: this.outcomeId(),
            timepoint: this.timepoint(),
            value_type: this.valueType,
          },
        });
  }

  private async save(): Promise<void> {
    const values = this.values();
    if (!values || !this.editable()) return;
    const result = await this.autosave.track(async () => {
      try {
        return await this.send(values);
      } catch (error) {
        // A save of the other group can bump this row on the server (e.g. the direction
        // sentence depends on both groups), or the row was created meanwhile. What the
        // person typed wins: take the newest version and save again, once.
        if (!(error instanceof HttpErrorResponse) || error.status !== 409) throw error;
        this.current = await this.latest();
        return await this.send(values);
      }
    });
    if (result) {
      this.current = result;
      this.saved.emit(result);
    }
  }
}
