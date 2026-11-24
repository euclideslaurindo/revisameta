import { Component, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Calibration, Point, toData } from './digitizer-math';

type Step = 'x1' | 'x2' | 'y1' | 'y2' | 'points';
const STEPS: Step[] = ['x1', 'x2', 'y1', 'y2', 'points'];

/**
 * Graph digitizer (P2, in the spirit of WebPlotDigitizer). The image stays in the
 * browser (never uploaded). The person clicks two known points on each axis, types
 * their values, then clicks the data points. Values read this way are approximate:
 * when used in the extraction, the source must be set to "digitized from a graph".
 */
@Component({
  selector: 'rm-plot-digitizer',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  template: `
    <h3>{{ 'digitizer.title' | transloco }}</h3>
    <p class="muted">{{ 'digitizer.intro' | transloco }}</p>
    <label class="file">
      {{ 'digitizer.pick' | transloco }}
      <input type="file" accept="image/*" (change)="pick($event)" />
    </label>
    @if (src()) {
      <p role="status">
        <strong>{{ 'digitizer.step.' + step() | transloco }}</strong>
      </p>
      <div class="row">
        @for (axis of ['x1', 'x2', 'y1', 'y2']; track axis) {
          <mat-form-field subscriptSizing="dynamic" class="axis">
            <mat-label>{{ 'digitizer.value.' + axis | transloco }}</mat-label>
            <input matInput inputmode="decimal" [(ngModel)]="values[axis]" />
          </mat-form-field>
        }
        <mat-checkbox [(ngModel)]="logX">{{ 'digitizer.logX' | transloco }}</mat-checkbox>
        <mat-checkbox [(ngModel)]="logY">{{ 'digitizer.logY' | transloco }}</mat-checkbox>
      </div>
      <div class="canvas">
        <img
          #image
          [src]="src()"
          [alt]="'digitizer.imageAlt' | transloco"
          tabindex="0"
          (click)="click($event)"
          (keydown)="(null)"
        />
        @for (m of marks(); track $index) {
          <span
            class="mark"
            [class.axis-mark]="m.axis"
            [style.left.px]="m.px"
            [style.top.px]="m.py"
          >
            {{ m.label }}
          </span>
        }
      </div>
      <div class="actions">
        <button mat-button type="button" (click)="undo()">
          {{ 'digitizer.undo' | transloco }}
        </button>
        <button mat-button type="button" (click)="reset()">
          {{ 'digitizer.reset' | transloco }}
        </button>
      </div>
      @if (error()) {
        <p class="warning" role="alert">{{ 'digitizer.error.' + error() | transloco }}</p>
      }
      @if (rows().length) {
        <table class="result-table">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">X</th>
              <th scope="col">Y</th>
            </tr>
          </thead>
          <tbody>
            @for (r of rows(); track $index) {
              <tr>
                <td>{{ $index + 1 }}</td>
                <td>{{ r.x }}</td>
                <td>{{ r.y }}</td>
              </tr>
            }
          </tbody>
        </table>
        <p class="warning">{{ 'digitizer.approximate' | transloco }}</p>
      }
    }
  `,
  styles: `
    .canvas {
      position: relative;
      display: inline-block;
      cursor: crosshair;
      max-width: 100%;
    }
    .canvas img {
      max-width: 100%;
      display: block;
    }
    .mark {
      position: absolute;
      transform: translate(-50%, -50%);
      background: var(--mat-sys-error);
      color: var(--mat-sys-on-error);
      border-radius: 8px;
      font-size: 0.7em;
      padding: 0 4px;
      pointer-events: none;
    }
    .axis-mark {
      background: var(--mat-sys-primary);
      color: var(--mat-sys-on-primary);
    }
    .axis {
      width: 120px;
    }
  `,
})
export class PlotDigitizer {
  private readonly transloco = inject(TranslocoService);
  private readonly image = viewChild<ElementRef<HTMLImageElement>>('image');

  protected readonly src = signal<string | null>(null);
  protected readonly clicks = signal<Point[]>([]);
  protected readonly error = signal<string | null>(null);
  protected values: Record<string, string> = { x1: '', x2: '', y1: '', y2: '' };
  protected logX = false;
  protected logY = false;

  protected readonly step = computed<Step>(() => STEPS[Math.min(this.clicks().length, 4)]);

  protected readonly marks = computed(() => {
    const img = this.image()?.nativeElement;
    const scale = img && img.naturalWidth ? img.clientWidth / img.naturalWidth : 1;
    return this.clicks().map((p, i) => ({
      px: p.x * scale,
      py: p.y * scale,
      axis: i < 4,
      label: i < 4 ? STEPS[i].toUpperCase() : String(i - 3),
    }));
  });

  protected readonly rows = computed(() => {
    this.clicks();
    const calibration = this.calibration();
    if (!calibration) return [];
    const lang = this.transloco.getActiveLang();
    return this.clicks()
      .slice(4)
      .map((p) => toData(p, calibration))
      .map((v) => ({ x: this.fmt(v.x, lang), y: this.fmt(v.y, lang) }));
  });

  private fmt(value: number, lang: string): string {
    return Number.isFinite(value)
      ? value.toLocaleString(lang.startsWith('en') ? 'en' : 'pt-BR', {
          maximumSignificantDigits: 4,
        })
      : '—';
  }

  private number(text: string): number | null {
    const v = Number(text.replace(',', '.'));
    return text.trim() && Number.isFinite(v) ? v : null;
  }

  private calibration(): Calibration | null {
    const c = this.clicks();
    if (c.length < 4) return null;
    const [x1, x2, y1, y2] = ['x1', 'x2', 'y1', 'y2'].map((k) => this.number(this.values[k]));
    if (x1 === null || x2 === null || y1 === null || y2 === null) {
      this.error.set('values');
      return null;
    }
    if (
      x1 === x2 ||
      y1 === y2 ||
      (this.logX && (x1 <= 0 || x2 <= 0)) ||
      (this.logY && (y1 <= 0 || y2 <= 0))
    ) {
      this.error.set('axes');
      return null;
    }
    this.error.set(null);
    return {
      x1: c[0],
      x2: c[1],
      y1: c[2],
      y2: c[3],
      vx1: x1,
      vx2: x2,
      vy1: y1,
      vy2: y2,
      logX: this.logX,
      logY: this.logY,
    };
  }

  pick(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const previous = this.src();
    if (previous) URL.revokeObjectURL(previous);
    this.src.set(URL.createObjectURL(file));
    this.reset();
  }

  click(event: MouseEvent): void {
    const img = this.image()?.nativeElement;
    if (!img) return;
    const rect = img.getBoundingClientRect();
    const scale = img.naturalWidth / rect.width;
    this.clicks.update((c) => [
      ...c,
      { x: (event.clientX - rect.left) * scale, y: (event.clientY - rect.top) * scale },
    ]);
  }

  undo(): void {
    this.clicks.update((c) => c.slice(0, -1));
  }

  reset(): void {
    this.clicks.set([]);
    this.error.set(null);
  }
}
