import { Component, DestroyRef, effect, inject, signal } from '@angular/core';
import { MatBadgeModule } from '@angular/material/badge';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { Router } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../core/api/api';
import { myNotifications } from '../core/api/fn/notifications/my-notifications';
import { readAllNotifications } from '../core/api/fn/notifications/read-all-notifications';
import { readNotification } from '../core/api/fn/notifications/read-notification';
import { NotificationOut } from '../core/api/models/notification-out';
import { AuthService } from '../core/auth/auth';

const EVERY_MS = 60_000;

/** In-app notifications: mentions, screening conflicts and the project deadline. */
@Component({
  selector: 'rm-notifications-menu',
  imports: [TranslocoPipe, MatBadgeModule, MatButtonModule, MatMenuModule],
  template: `
    <button
      mat-button
      type="button"
      [matMenuTriggerFor]="menu"
      [matBadge]="unread() || null"
      matBadgeColor="warn"
      [attr.aria-label]="'notifications.open' | transloco: { n: unread() }"
      (menuOpened)="refresh()"
    >
      {{ 'notifications.title' | transloco }}
    </button>
    <mat-menu #menu="matMenu" class="notifications">
      @if (unread()) {
        <button mat-menu-item type="button" (click)="readAll()">
          {{ 'notifications.readAll' | transloco }}
        </button>
      }
      @for (n of items(); track n.id) {
        <button mat-menu-item type="button" (click)="open(n)" [class.unread]="!n.read">
          <span class="project">{{ n.project_title }}</span>
          <span>{{ 'notifications.kind.' + n.kind | transloco: n.payload }}</span>
        </button>
      } @empty {
        <p class="muted empty">{{ 'notifications.empty' | transloco }}</p>
      }
    </mat-menu>
  `,
  styles: `
    .unread {
      font-weight: 600;
    }
    .project {
      display: block;
      font-size: 0.8em;
      opacity: 0.7;
    }
    .empty {
      padding: 8px 16px;
    }
  `,
})
export class NotificationsMenu {
  private readonly api = inject(Api);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly unread = signal(0);
  protected readonly items = signal<NotificationOut[]>([]);

  constructor() {
    const timer = setInterval(() => void this.refresh(), EVERY_MS);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
    effect(() => {
      if (this.auth.user()) void this.refresh();
    });
  }

  async refresh(): Promise<void> {
    if (!this.auth.user()) return;
    try {
      const out = await this.api.invoke(myNotifications, {});
      this.unread.set(out.unread);
      this.items.set(out.items);
    } catch {
      // A failed refresh is retried on the next tick; nothing to show the user.
    }
  }

  async readAll(): Promise<void> {
    await this.api.invoke(readAllNotifications, {});
    await this.refresh();
  }

  async open(n: NotificationOut): Promise<void> {
    if (!n.read) await this.api.invoke(readNotification, { notification_id: n.id });
    const base = ['/projetos', n.project_id];
    const p = n.payload as Record<string, string>;
    if (n.kind === 'mention' && p['entity'] === 'study') {
      await this.router.navigate([...base, 'estudos', p['entity_id']]);
    } else if (n.kind === 'mention' && p['entity'] === 'analysis') {
      await this.router.navigate([...base, 'meta-analise']);
    } else if (n.kind === 'mention' || n.kind === 'screening_conflict') {
      await this.router.navigate([...base, 'triagem']);
    } else {
      await this.router.navigate(base);
    }
    await this.refresh();
  }
}
