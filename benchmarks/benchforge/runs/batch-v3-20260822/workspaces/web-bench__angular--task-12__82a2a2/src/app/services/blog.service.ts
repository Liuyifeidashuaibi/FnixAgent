import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Blog } from '../models/blog.model';

@Injectable({ providedIn: 'root' })
export class BlogService {
  private blogsSubject = new BehaviorSubject<Blog[]>([
    { id: '1', title: 'Getting Started with Angular', content: 'Angular is a powerful framework.', author: 'Alice', date: '2024-01-15' },
    { id: '2', title: 'TypeScript Best Practices', content: 'TypeScript improves code quality.', author: 'Bob', date: '2024-02-20' },
    { id: '3', title: 'RxJS for Beginners', content: 'RxJS handles async operations.', author: 'Charlie', date: '2024-03-10' },
  ]);

  blogs$: Observable<Blog[]> = this.blogsSubject.asObservable();

  getBlogs(): Blog[] {
    return this.blogsSubject.getValue();
  }

  getBlog(id: string): Blog | undefined {
    return this.blogsSubject.getValue().find(b => b.id === id);
  }

  addBlog(blog: Blog): void {
    const blogs = [...this.blogsSubject.getValue(), blog];
    this.blogsSubject.next(blogs);
  }

  updateBlog(updatedBlog: Blog): void {
    const blogs = this.blogsSubject.getValue().map(b =>
      b.id === updatedBlog.id ? updatedBlog : b
    );
    this.blogsSubject.next(blogs);
  }

  deleteBlog(id: string): void {
    const blogs = this.blogsSubject.getValue().filter(b => b.id !== id);
    this.blogsSubject.next(blogs);
  }
}
