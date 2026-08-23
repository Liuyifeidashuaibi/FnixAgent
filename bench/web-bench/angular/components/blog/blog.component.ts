import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-blog',
  template: `<div class="blog-title">{{ title }}</div>
  <div>{{ detail }}</div>`,
  styles: [`.blog-title {
    width: fit-content;
    font-size: 24px;
    margin-bottom: 10px;
  }`]
})
export class BlogComponent {
  @Input() title!: string;
  @Input() detail!: string;
}