import { Injectable, signal } from '@angular/core';

export type ThemeChoice = 'auto' | 'light' | 'dark';
const STORE = 'rm.theme';

/**
 * Light / dark / follow the device. A per-device convenience kept in localStorage
 * (it may be unavailable in private mode; then the choice lasts until reload).
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly choice = signal<ThemeChoice>(this.read());

  constructor() {
    this.apply(this.choice());
  }

  set(choice: ThemeChoice): void {
    this.choice.set(choice);
    this.apply(choice);
    try {
      localStorage.setItem(STORE, choice);
    } catch {
      // Private mode: nothing to persist.
    }
  }

  private read(): ThemeChoice {
    try {
      const v = localStorage.getItem(STORE);
      return v === 'light' || v === 'dark' ? v : 'auto';
    } catch {
      return 'auto';
    }
  }

  private apply(choice: ThemeChoice): void {
    const root = document.documentElement;
    if (choice === 'auto') delete root.dataset['theme'];
    else root.dataset['theme'] = choice;
  }
}
