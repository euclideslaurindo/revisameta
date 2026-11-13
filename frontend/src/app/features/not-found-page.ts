import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

@Component({
  selector: 'rm-not-found-page',
  imports: [RouterLink, TranslocoPipe],
  template: `
    <h1>{{ 'notFound.title' | transloco }}</h1>
    <a routerLink="/">{{ 'notFound.back' | transloco }}</a>
  `,
})
export class NotFoundPage {}
