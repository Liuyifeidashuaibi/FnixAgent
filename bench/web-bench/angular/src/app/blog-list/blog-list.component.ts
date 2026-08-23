import { Component, Input, Output, EventEmitter } from '@angular/core';

@Component({
  selector: 'app-blog-list',
  template: `
    <div class='list-item' *ngFor="let blog of blogs" (click)="selectBlog(blog)">
      {{ blog.title }}
    </div>
  `,
  styles: [`.list-item {
    height: 40px;
    width: 300px;
    border-box: border-box;
    padding: 10px;
    box-sizing: border-box;
    margin-bottom: 5px;
    background-color: #f0f0f0;
    border: 1px solid #ccc;
    cursor: pointer;
  }

  .selected {
    background-color: #007bff;
    color: white;
    font-weight: bold;
  }`]
})
export class BlogListComponent {
  @Input() blogs: any[] = [];
  @Output() selectedBlogChange = new EventEmitter<any>();

  selectBlog(blog: any) {
    this.selectedBlogChange.emit(blog);
  }
}