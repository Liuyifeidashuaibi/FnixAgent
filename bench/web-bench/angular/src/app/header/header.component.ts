import { Component } from '@angular/core';

@Component({
  selector: 'app-header',
  template: `
    <div class="header">
      <h1>Hello Blog</h1>
      <button class="add-blog-btn" (click)="openBlogForm()">Add Blog</button>
    </div>
  `,
  styles: [`.header {
    background-color: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 10px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .add-blog-btn {
    background-color: #007BFF;
    color: white;
    padding: 10px 15px;
    border: none;
    cursor: pointer;
    border-radius: 4px;
  }

  .add-blog-btn:hover {
    background-color: #0056b3;
  }
`]
})
export class HeaderComponent {
  openBlogForm() {
    // Logic to open the blog form
  }
}