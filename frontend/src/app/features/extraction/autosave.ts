import { Injectable, computed, signal } from '@angular/core';

/** Tracks autosave state for the whole extraction page ("Salvo" / "Salvando…" / error). */
@Injectable()
export class AutosaveState {
  private readonly pending = signal(0);
  readonly dirty = signal(0);
  readonly error = signal<unknown>(null);
  /** Increments after every successful save; pages use it to refresh alerts. */
  readonly saved = signal(0);
  readonly saving = computed(() => this.pending() > 0);
  readonly status = computed<'saving' | 'unsaved' | 'error' | 'saved'>(() => {
    if (this.error()) return 'error';
    if (this.pending() > 0) return 'saving';
    if (this.dirty() > 0) return 'unsaved';
    return 'saved';
  });

  markDirty(): void {
    this.dirty.update((n) => n + 1);
  }

  async track<T>(action: () => Promise<T>): Promise<T | null> {
    this.pending.update((n) => n + 1);
    try {
      const result = await action();
      this.error.set(null);
      this.dirty.set(0);
      this.saved.update((n) => n + 1);
      return result;
    } catch (error) {
      this.error.set(error);
      return null;
    } finally {
      this.pending.update((n) => n - 1);
    }
  }
}
