import { Component } from '@angular/core';
import { HeaderComponent } from './components/header/header.component';
import { MainComponent } from './components/main/main.component';
import { BlogComponent } from './components/blog/blog.component';

@Component({
  selector: 'app-root',
  template: `<app-header></app-header>
            <app-main>
              <app-blog [title]="mockTitle" [detail]="mockDetail"></app-blog>
            </app-main>`,
  styleUrls: ['./app.component.css'],
  imports: [HeaderComponent, MainComponent, BlogComponent]
})
export class AppComponent {
  mockTitle = 'Morning';
  mockDetail = 'Morning My Friends';
}
