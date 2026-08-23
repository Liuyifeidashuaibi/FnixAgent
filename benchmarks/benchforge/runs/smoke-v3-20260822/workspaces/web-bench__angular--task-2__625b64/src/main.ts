import { Component } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { MainComponent } from './main.component';

@Component({
  selector: 'app-root',
  template: '<app-main></app-main>',
  standalone: true,
  imports: [MainComponent]
})
export class AppComponent {}

bootstrapApplication(AppComponent);
