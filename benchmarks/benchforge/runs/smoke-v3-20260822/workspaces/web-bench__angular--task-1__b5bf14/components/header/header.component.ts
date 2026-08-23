import { Component } from '@angular/core';

@Component({
  selector: 'app-header',
  template: `
    <div class="header">
      <h1>Hello Blog</h1>
    </div>
  `,
  styles: [`
    .header {
      background-color: #4a90d9;
      color: #ffffff;
      padding: 20px 30px;
      text-align: center;
      font-size: 32px;
      font-weight: bold;
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
  `]
})
export class HeaderComponent {
}
