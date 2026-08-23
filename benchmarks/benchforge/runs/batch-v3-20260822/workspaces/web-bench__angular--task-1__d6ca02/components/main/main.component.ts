import { Component } from '@angular/core';
import { BlogComponent } from '../blog/blog.component';
import { NgFor } from '@angular/common';

@Component({
  selector: 'app-main',
  standalone: true,
  imports: [BlogComponent, NgFor],
  template: `
    <div class="main-container">
      <app-blog
        *ngFor="let blog of blogs"
        [title]="blog.title"
        [detail]="blog.detail"
      ></app-blog>
    </div>
  `,
  styles: [`
    .main-container {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      justify-content: flex-start;
      flex: 1;
      padding: 16px;
      overflow-y: auto;
    }
  `]
})
export class MainComponent {
  blogs = [
    { title: 'Morning', detail: 'Morning My Friends' }
  ];
}
