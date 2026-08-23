import { Component } from '@angular/core';

@Component({
  selector: 'app-header',
  template: `
    <div class="header-container">
      <h1>Hello Blog</h1>
    </div>
  `,
  styles: [`
    .header-container {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      padding: 20px 30px;
      text-align: center;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }
    .header-container h1 {
      margin: 0;
      font-size: 28px;
      font-weight: 600;
      letter-spacing: 1px;
    }
  `]
})
export class HeaderComponent {}
