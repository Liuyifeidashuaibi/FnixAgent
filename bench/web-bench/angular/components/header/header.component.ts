import { Component } from '@angular/core';

@Component({
  selector: 'app-header',
  template: `<div class="header-container">Hello Blog</div>`,
  styles: [`.header-container {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 20px;
    text-align: center;
    font-size: 24px;
  }`]
})
export class HeaderComponent {}