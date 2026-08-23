import { Component } from '@angular/core';
import { HeaderComponent } from './components/header/header.component';
import { MainComponent } from './components/main/main.component';

@Component({
  selector: 'app-root',
  template: `<app-header></app-header>
  <app-main></app-main>`,
  styleUrls: ['./app.component.css']
})
export class AppComponent { }
