import { Component, OnInit } from '@angular/core';
import { BlogService } from '../services/blog.service';
import { Blog } from '../models/blog.model';

@Component({
  selector: 'app-blog-form',
  template: `
    <form (ngSubmit)="onSubmit()" #blogForm="ngForm">
      <h2>New Blog</h2>
      <div>
        <label>Title:</label>
        <input [(ngModel)]="title" name="title" required />
      </div>
      <div>
        <label>Author:</label>
        <input [(ngModel)]="author" name="author" required />
      </div>
      <div>
        <label>Category:</label>
        <input [(ngModel)]="category" name="category" />
      </div>
      <div>
        <label>Excerpt:</label>
        <textarea [(ngModel)]="excerpt" name="excerpt"></textarea>
      </div>
      <div>
        <label>Content:</label>
        <textarea [(ngModel)]="content" name="content"></textarea>
      </div>
      <p *ngIf="duplicateError" class="error">{{ duplicateError }}</p>
      <button type="submit" [disabled]="!title || !author">Submit</button>
    </form>
  `,
  styles: [`
    .error { color: red; }
    form { max-width: 500px; margin: 0 auto; }
    div { margin-bottom: 10px; }
    label { display: block; font-weight: bold; }
    input, textarea { width: 100%; padding: 5px; }
  `]
})
export class BlogFormComponent implements OnInit {
  title = '';
  author = '';
  category = '';
  excerpt = '';
  content = '';
  duplicateError = '';

  constructor(private blogService: BlogService) {}

  ngOnInit(): void {}

  onSubmit(): void {
    // Title duplication check
    const blogs = this.blogService.getBlogs();
    const isDuplicate = blogs.some(blog => blog.title.toLowerCase() === this.title.trim().toLowerCase());

    if (isDuplicate) {
      this.duplicateError = 'A blog with this title already exists.';
      return;
    }

    this.duplicateError = '';

    const newBlog: Blog = {
      id: Date.now().toString(),
      title: this.title.trim(),
      date: new Date().toISOString().split('T')[0],
      excerpt: this.excerpt,
      content: this.content,
      author: this.author,
      category: this.category
    };

    this.blogService.addBlog(newBlog);
    this.title = '';
    this.author = '';
    this.category = '';
    this.excerpt = '';
    this.content = '';
  }
}
