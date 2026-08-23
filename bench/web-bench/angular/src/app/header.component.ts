import { Component } from '@angular/core';

@Component({
  selector: 'app-header',
  template: `
    <div class="header">
      <h1>Hello Blog</h1>
      <span class="blog-list-len">{{ blogCount }}</span>
    </div>
  `,
  styles: [`.header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 20px;
    text-align: center;
    position: relative;
  }

  .blog-list-len {
    position: absolute;
    right: 20px;
    top: 20px;
    font-size: 14px;
    color: #fff;
  }`]
})
export class HeaderComponent {
  blogCount = 0;
}