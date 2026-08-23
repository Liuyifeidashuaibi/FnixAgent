import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface Blog {
  id: number;
  title: string;
  content: string;
  author: string;
  date: string;
}

@Component({
  selector: 'app-blog-list',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="blog-list">
      <div *ngFor="let blog of filteredBlogs" class="blog-item">
        <h3>{{ blog.title }}</h3>
        <p class="author">By {{ blog.author }} | {{ blog.date }}</p>
        <p class="content">{{ blog.content }}</p>
      </div>
      <p *ngIf="filteredBlogs.length === 0" class="no-results">No blogs found.</p>
    </div>
  `,
  styles: [`
    .blog-list {
      padding: 16px;
    }
    .blog-item {
      border: 1px solid var(--border, #ddd);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
    }
    .blog-item h3 {
      margin: 0 0 8px;
    }
    .author {
      color: #666;
      font-size: 0.9em;
      margin: 0 0 8px;
    }
    .content {
      margin: 0;
    }
    .no-results {
      text-align: center;
      color: #999;
      padding: 32px;
    }
  `]
})
export class BlogListComponent {
  @Input() blogs: Blog[] = [];
  @Input() searchTerm: string = '';

  get filteredBlogs(): Blog[] {
    if (!this.searchTerm) {
      return this.blogs;
    }
    const term = this.searchTerm.toLowerCase();
    return this.blogs.filter(blog =>
      blog.title.toLowerCase().includes(term) ||
      blog.content.toLowerCase().includes(term) ||
      blog.author.toLowerCase().includes(term)
    );
  }
}
