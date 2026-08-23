import { Injectable } from '@angular/core';
import { Blog } from '../models/blog.model';

@Injectable({
  providedIn: 'root'
})
export class BlogService {
  private blogs: Blog[] = [
    {
      id: 1,
      title: 'Getting Started with Angular: A Comprehensive Guide for Beginners in 2024',
      content: 'Angular is a powerful framework for building web applications...',
      author: 'John Doe',
      date: '2024-01-15'
    },
    {
      id: 2,
      title: 'Advanced TypeScript Techniques Every Developer Should Know About When Working with Large Scale Applications',
      content: 'TypeScript offers many advanced features that can help...',
      author: 'Jane Smith',
      date: '2024-02-20'
    },
    {
      id: 3,
      title: 'Short Title',
      content: 'This blog has a short title that should not be truncated at all.',
      author: 'Bob Wilson',
      date: '2024-03-10'
    },
    {
      id: 4,
      title: 'Understanding RxJS Observables and How They Transform the Way We Handle Asynchronous Data Streams in Modern Web Applications',
      content: 'RxJS is a library for reactive programming using Observables...',
      author: 'Alice Chen',
      date: '2024-04-05'
    },
    {
      id: 5,
      title: 'CSS Grid vs Flexbox',
      content: 'A comparison of CSS layout techniques.',
      author: 'Tom Brown',
      date: '2024-05-12'
    },
    {
      id: 6,
      title: 'Building Scalable Enterprise Applications with Angular, NgRx, and Micro-Frontend Architecture: Best Practices and Lessons Learned from Production',
      content: 'In this article we explore enterprise patterns...',
      author: 'Sarah Lee',
      date: '2024-06-18'
    }
  ];

  getBlogs(): Blog[] {
    return this.blogs;
  }

  getBlogById(id: number): Blog | undefined {
    return this.blogs.find(blog => blog.id === id);
  }
}
