import { Component } from '@angular/core';

@Component({
  selector: 'app-main',
  template: `<div class="main-content">
    <app-blog [title]="blog.title" [detail]="blog.detail"></app-blog>
  </div>`,
  styles: [`.main-content {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    padding: 20px;
  }`]
})
export class MainComponent {
  blog = { title: 'Morning', detail: 'Morning My Friends' };
}