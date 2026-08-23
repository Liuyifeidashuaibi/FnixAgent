import { Injectable } from '@angular/core';

export interface Blog {
  id: number;
  title: string;
  content: string;
}

@Injectable({
  providedIn: 'root'
})
export class BlogService {
  private blogs: Blog[] = [
    { id: 1, title: 'Getting Started with Angular', content: 'Angular is a powerful framework...' },
    { id: 2, title: 'TypeScript Best Practices', content: 'TypeScript adds static types...' },
    { id: 3, title: 'RxJS Operators Explained', content: 'RxJS is a library for reactive programming...' }
  ];

  getBlogs(): Blog[] {
    return this.blogs;
  }

  getBlogById(id: number): Blog | undefined {
    return this.blogs.find(blog => blog.id === id);
  }

  deleteBlog(id: number): void {
    this.blogs = this.blogs.filter(blog => blog.id !== id);
  }
}
