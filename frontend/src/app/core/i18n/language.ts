import { DOCUMENT, Injectable, inject } from '@angular/core';
import { TranslocoService } from '@jsverse/transloco';

export type Language = 'pt-BR' | 'en';
export const LANGUAGES: readonly Language[] = ['pt-BR', 'en'];
const STORAGE_KEY = 'rm.lang';

/** Picks the interface language: saved choice, then the browser, then pt-BR (ADR-008). */
export function detectLanguage(saved: string | null, browser: readonly string[]): Language {
  if (saved === 'pt-BR' || saved === 'en') {
    return saved;
  }
  for (const tag of browser) {
    const lower = tag.toLowerCase();
    if (lower.startsWith('pt')) return 'pt-BR';
    if (lower.startsWith('en')) return 'en';
  }
  return 'pt-BR';
}

@Injectable({ providedIn: 'root' })
export class LanguageService {
  private readonly transloco = inject(TranslocoService);
  private readonly document = inject(DOCUMENT);

  current(): Language {
    return this.transloco.getActiveLang() as Language;
  }

  init(): void {
    let saved: string | null;
    try {
      saved = localStorage.getItem(STORAGE_KEY);
    } catch {
      saved = null;
    }
    this.apply(detectLanguage(saved, navigator.languages ?? [navigator.language]));
  }

  set(language: Language): void {
    try {
      localStorage.setItem(STORAGE_KEY, language);
    } catch {
      // Storage may be blocked; the choice still applies to this visit.
    }
    this.apply(language);
  }

  private apply(language: Language): void {
    this.transloco.setActiveLang(language);
    this.document.documentElement.lang = language;
  }
}
