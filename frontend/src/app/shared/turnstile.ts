import {
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  inject,
  input,
  output,
  viewChild,
} from '@angular/core';

interface TurnstileApi {
  render(element: HTMLElement, options: Record<string, unknown>): string;
  remove(widgetId: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

const SCRIPT_URL = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
let scriptLoading: Promise<void> | null = null;

function loadScript(): Promise<void> {
  scriptLoading ??= new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = SCRIPT_URL;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('turnstile'));
    document.head.appendChild(script);
  });
  return scriptLoading;
}

/** Free Cloudflare Turnstile captcha. Rendered only when the backend enables it. */
@Component({
  selector: 'rm-turnstile',
  template: `<div #box></div>`,
})
export class Turnstile {
  readonly siteKey = input.required<string>();
  readonly language = input<string>('pt-BR');
  readonly token = output<string | null>();

  private readonly box = viewChild.required<ElementRef<HTMLElement>>('box');
  private widgetId: string | null = null;

  constructor() {
    afterNextRender(async () => {
      await loadScript();
      this.widgetId =
        window.turnstile?.render(this.box().nativeElement, {
          sitekey: this.siteKey(),
          language: this.language() === 'en' ? 'en' : 'pt-br',
          callback: (value: string) => this.token.emit(value),
          'expired-callback': () => this.token.emit(null),
          'error-callback': () => this.token.emit(null),
        }) ?? null;
    });
    inject(DestroyRef).onDestroy(() => {
      if (this.widgetId) window.turnstile?.remove(this.widgetId);
    });
  }
}
