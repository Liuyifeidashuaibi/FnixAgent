import { Component } from '@angular/core';

@Component({
  selector: 'app-root',
  template: `
    <div class="app-container">
      <header class="app-header">
        <h1>Blog Application</h1>
      </header>
      <main class="app-content">
        <app-blog></app-blog>
      </main>
    </div>
  `,
  styles: [`
    .app-container {
      max-width: 900px;
      margin: 0 auto;
      padding: 20px;
      font-family: Arial, sans-serif;
    }
    .app-header {
      text-align: center;
      padding: 20px 0;
      border-bottom: 2px solid #e0e0e0;
      margin-bottom: 30px;
    }
    .app-header h1 {
      color: #333;
      margin: 0;
    }
    .app-content {
      padding: 20px 0;
    }
  `]
})
export class AppComponent {}
