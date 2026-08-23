import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-blog',
  template: `<div class="blog-container">
    <h2 class="blog-title">{{ title }}</h2>
    <p>{{ detail }}</p>
  </div>`,
  styles: [`.blog-container {
    margin: 20px;
  }

  .blog-title {
    width: fit-content;
    font-size: 24px;
  }`]
})
export class BlogComponent {
  @Input() title!: string;
  @Input() detail!: string;
}
