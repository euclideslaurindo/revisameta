import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { listUsers } from '../../core/api/fn/admin/list-users';
import { overview } from '../../core/api/fn/admin/overview';
import { updateUser } from '../../core/api/fn/admin/update-user';
import { setQuota } from '../../core/api/fn/quotas/set-quota';
import { userUsage } from '../../core/api/fn/quotas/user-usage';
import { health } from '../../core/api/fn/system/health';
import { AdminOverview } from '../../core/api/models/admin-overview';
import { AdminUserOut } from '../../core/api/models/admin-user-out';
import { UsageOut } from '../../core/api/models/usage-out';
import { AuthService } from '../../core/auth/auth';
import { FormError } from '../../shared/form-error';

const KINDS = ['projects', 'storage_mb', 'ai_calls'] as const;
type Kind = (typeof KINDS)[number];
interface Check {
  name: string;
  status: string;
  detail: string;
}

/** System administration (screen 21): service status, users and quotas. No project content. */
@Component({
  selector: 'rm-admin-page',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSlideToggleModule,
    FormError,
  ],
  template: `
    <h1>{{ 'admin.title' | transloco }}</h1>
    <p class="muted">{{ 'admin.intro' | transloco }}</p>
    <rm-form-error [error]="error()" />

    <mat-card class="block">
      <mat-card-content>
        <h2>{{ 'admin.status' | transloco }}</h2>
        <ul>
          @for (c of checks(); track c.name) {
            <li>
              <strong>{{ 'admin.services.' + c.name | transloco }}</strong>:
              <span [class]="c.status === 'ok' ? 'ok' : 'bad'">{{
                'admin.state.' + c.status | transloco
              }}</span>
              @if (c.detail) {
                <span class="muted"> ({{ c.detail }})</span>
              }
            </li>
          } @empty {
            <li>{{ 'admin.state.down' | transloco }}</li>
          }
        </ul>
        <button mat-stroked-button type="button" (click)="loadHealth()">
          {{ 'admin.refresh' | transloco }}
        </button>
      </mat-card-content>
    </mat-card>

    @if (stats(); as s) {
      <mat-card class="block">
        <mat-card-content>
          <h2>{{ 'admin.overview' | transloco }}</h2>
          <p>
            {{ 'admin.counts' | transloco: s }}
          </p>
          <p class="muted">
            {{
              'admin.defaults'
                | transloco
                  : {
                      projects: s.default_quotas['projects'],
                      storage: s.default_quotas['storage_mb'],
                      ai: s.default_quotas['ai_calls'],
                    }
            }}
          </p>
        </mat-card-content>
      </mat-card>
    }

    <mat-card class="block">
      <mat-card-content>
        <h2>{{ 'admin.users' | transloco }}</h2>
        <form class="row" (ngSubmit)="search(0)">
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'admin.search' | transloco }}</mat-label>
            <input matInput name="q" [ngModel]="query()" (ngModelChange)="query.set($event)" />
          </mat-form-field>
          <button mat-stroked-button type="submit">{{ 'admin.searchButton' | transloco }}</button>
        </form>
        <p class="muted">{{ 'admin.total' | transloco: { total: total() } }}</p>
        <div class="table-wrap">
          <table class="result-table">
            <thead>
              <tr>
                <th>{{ 'admin.col.name' | transloco }}</th>
                <th>{{ 'admin.col.email' | transloco }}</th>
                <th>{{ 'admin.col.created' | transloco }}</th>
                <th>{{ 'admin.col.projects' | transloco }}</th>
                <th>{{ 'admin.col.active' | transloco }}</th>
                <th>{{ 'admin.col.admin' | transloco }}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (u of users(); track u.id) {
                <tr>
                  <td>{{ u.name }}</td>
                  <td>
                    {{ u.email }}
                    @if (!u.email_verified) {
                      <span class="muted">({{ 'admin.unverified' | transloco }})</span>
                    }
                  </td>
                  <td>{{ u.created_at.slice(0, 10) }}</td>
                  <td>{{ u.projects_owned }}</td>
                  <td>
                    <mat-slide-toggle
                      [checked]="u.is_active"
                      [disabled]="busy() || u.id === me()"
                      (change)="toggle(u, 'is_active', $event.checked)"
                      [attr.aria-label]="'admin.col.active' | transloco"
                    />
                  </td>
                  <td>
                    <mat-slide-toggle
                      [checked]="u.is_system_admin"
                      [disabled]="busy() || u.id === me()"
                      (change)="toggle(u, 'is_system_admin', $event.checked)"
                      [attr.aria-label]="'admin.col.admin' | transloco"
                    />
                  </td>
                  <td>
                    <button mat-button type="button" (click)="openQuotas(u)">
                      {{ 'admin.quotas' | transloco }}
                    </button>
                  </td>
                </tr>
                @if (open() === u.id && usage(); as use) {
                  <tr>
                    <td colspan="7">
                      <div class="row">
                        @for (k of kinds; track k) {
                          <mat-form-field subscriptSizing="dynamic">
                            <mat-label
                              >{{ 'admin.kind.' + k | transloco }} ({{
                                'admin.used' | transloco: { used: use[k].used }
                              }})</mat-label
                            >
                            <input
                              matInput
                              type="number"
                              min="0"
                              [name]="k"
                              [ngModel]="limits()[k]"
                              (ngModelChange)="setLimit(k, $event)"
                            />
                          </mat-form-field>
                        }
                        <button
                          mat-flat-button
                          type="button"
                          [disabled]="busy()"
                          (click)="saveQuotas(u)"
                        >
                          {{ 'admin.saveQuotas' | transloco }}
                        </button>
                      </div>
                      <p class="muted">{{ 'admin.quotaHint' | transloco }}</p>
                    </td>
                  </tr>
                }
              }
            </tbody>
          </table>
        </div>
        <div class="actions">
          <button
            mat-button
            type="button"
            [disabled]="offset() === 0"
            (click)="search(offset() - 50)"
          >
            {{ 'admin.previous' | transloco }}
          </button>
          <button
            mat-button
            type="button"
            [disabled]="offset() + 50 >= total()"
            (click)="search(offset() + 50)"
          >
            {{ 'admin.next' | transloco }}
          </button>
        </div>
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    .ok {
      color: var(--rm-ok, #1b5e20);
      font-weight: 600;
    }
    .bad {
      color: var(--rm-error, #b71c1c);
      font-weight: 600;
    }
    .row {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      align-items: center;
    }
    .table-wrap {
      overflow-x: auto;
    }
  `,
})
export class AdminPage implements OnInit {
  private readonly api = inject(Api);
  private readonly auth = inject(AuthService);

  protected readonly kinds = KINDS;
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly checks = signal<Check[]>([]);
  protected readonly stats = signal<AdminOverview | null>(null);
  protected readonly users = signal<AdminUserOut[]>([]);
  protected readonly total = signal(0);
  protected readonly offset = signal(0);
  protected readonly query = signal('');
  protected readonly open = signal<string | null>(null);
  protected readonly usage = signal<UsageOut | null>(null);
  protected readonly limits = signal<Record<Kind, number | null>>({
    projects: null,
    storage_mb: null,
    ai_calls: null,
  });

  protected me(): string | undefined {
    return this.auth.user()?.id;
  }

  async ngOnInit(): Promise<void> {
    await Promise.all([this.loadHealth(), this.loadOverview(), this.search(0)]);
  }

  async loadHealth(): Promise<void> {
    let body: unknown;
    try {
      body = await this.api.invoke(health, {});
    } catch (error) {
      // 503 still carries the per-service status.
      body = error instanceof HttpErrorResponse ? error.error : null;
    }
    const checks = (body as { checks?: Record<string, Record<string, unknown>> } | null)?.checks;
    this.checks.set(
      Object.entries(checks ?? {}).map(([name, c]) => ({
        name,
        status: String(c['status'] ?? 'down'),
        detail: c['r_version'] ? `R ${String(c['r_version'])}` : '',
      })),
    );
  }

  private async loadOverview(): Promise<void> {
    await this.run(async () => this.stats.set(await this.api.invoke(overview, {})));
  }

  async search(offset: number): Promise<void> {
    await this.run(async () => {
      const page = await this.api.invoke(listUsers, {
        q: this.query().trim() || undefined,
        offset: Math.max(0, offset),
      });
      this.users.set(page.items);
      this.total.set(page.total);
      this.offset.set(page.offset);
      this.open.set(null);
    });
  }

  async toggle(user: AdminUserOut, field: 'is_active' | 'is_system_admin', value: boolean) {
    await this.run(async () => {
      const updated = await this.api.invoke(updateUser, {
        user_id: user.id,
        body: { [field]: value },
      });
      this.users.update((list) => list.map((u) => (u.id === updated.id ? updated : u)));
    });
    if (this.error()) await this.search(this.offset());
  }

  async openQuotas(user: AdminUserOut): Promise<void> {
    if (this.open() === user.id) {
      this.open.set(null);
      return;
    }
    await this.run(async () => {
      const use = await this.api.invoke(userUsage, { user_id: user.id });
      this.usage.set(use);
      this.limits.set({
        projects: use.projects.limit,
        storage_mb: use.storage_mb.limit,
        ai_calls: use.ai_calls.limit,
      });
      this.open.set(user.id);
    });
  }

  protected setLimit(kind: Kind, value: number | string | null): void {
    const n = value === '' || value === null ? null : Number(value);
    this.limits.update((l) => ({ ...l, [kind]: Number.isFinite(n) ? n : null }));
  }

  async saveQuotas(user: AdminUserOut): Promise<void> {
    await this.run(async () => {
      for (const kind of KINDS) {
        const limit = this.limits()[kind];
        await this.api.invoke(setQuota, {
          user_id: user.id,
          body: { kind, limit: limit === null ? null : Math.max(0, Math.round(limit)) },
        });
      }
      this.open.set(null);
    });
  }

  private async run(action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await action();
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
