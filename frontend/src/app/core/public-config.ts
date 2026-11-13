import { Injectable, inject, signal } from '@angular/core';

import { Api } from './api/api';
import { publicConfig } from './api/fn/system/public-config';
import { PublicConfig } from './api/models/public-config';

@Injectable({ providedIn: 'root' })
export class PublicConfigService {
  private readonly api = inject(Api);
  readonly config = signal<PublicConfig | null>(null);

  async load(): Promise<void> {
    try {
      this.config.set(await this.api.invoke(publicConfig));
    } catch {
      this.config.set(null);
    }
  }

  captchaSiteKey(): string | null {
    const config = this.config();
    return config?.turnstile_enabled && config.turnstile_site_key ? config.turnstile_site_key : null;
  }
}
