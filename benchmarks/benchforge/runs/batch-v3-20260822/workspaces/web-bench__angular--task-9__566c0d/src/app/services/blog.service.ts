import { Injectable } from '@angular/core';
import { Blog } from '../models/blog.model';

@Injectable({
  providedIn: 'root'
})
export class BlogService {
  private blogs: Blog[] = [
    { id: 1, title: 'First Blog', content: 'This is the first blog post.', author: 'Alice', date: '2024-01-01' },
    { id: 2, title: 'Second Blog', content: 'This is the second blog post.', author: 'Bob', date: '2024-01-02' },
    { id: 3, title: 'Third Blog', content: 'This is the third blog post.', author: 'Charlie', date: '2024-01-03' }
  ];

  private nextId = 4;

  getBlogs(): Blog[] {
    return this.blogs;
  }

  getBlogById(id: number): Blog | undefined {
    return this.blogs.find(blog => blog.id === id);
  }

  addBlog(blog: Omit<Blog, 'id'>): Blog {
    const newBlog: Blog = { ...blog, id: this.nextId++ };
    this.blogs.push(newBlog);
    return newBlog;
  }

  updateBlog(id: number, updatedBlog: Omit<Blog, 'id'>): Blog | undefined {
    const index = this.blogs.findIndex(blog => blog.id === id);
    if (index === -1) return undefined;
    this.blogs[index] = { ...updatedBlog, id };
    return this.blogs[index];
  }

  deleteBlog(id: number): boolean {
    const index = this.blogs.findIndex(blog => blog.id === id);
    if (index === -1) return false;
    this.blogs.splice(index, 1);
    return true;
  }
}
