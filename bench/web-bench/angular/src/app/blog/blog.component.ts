import { Component, Input, Output, EventEmitter } from '@angular/core';

@Component({
  selector: 'app-blog',
  template: `
    <div class='blog-title'>{{ blog.title }}</div>
    <div>{{ blog.detail }}</div>
    <button class="delete-btn" (click)="onDelete()">Delete</button>
  `,
  styles: [`.blog-title {
    width: fit-content;
    font-size: 24px;
    margin-bottom: 10px;
  }

  .delete-btn {
    background-color: #dc3545;
    color: white;
    padding: 8px 12px;
    border: none;
    cursor: pointer;
    border-radius: 4px;
    margin-top: 10px;
  }

  .delete-btn:hover {
    background-color: #c82333;
  }`]
})
export class BlogComponent {
  @Input() blog: any;
  @Output() deleteBlog = new EventEmitter<string>();

  onDelete() {
    this.deleteBlog.emit(this.blog.id);
  }
}