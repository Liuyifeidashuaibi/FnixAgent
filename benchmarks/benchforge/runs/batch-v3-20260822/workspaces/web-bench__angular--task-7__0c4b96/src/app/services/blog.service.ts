import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Blog } from '../models/blog.model';

@Injectable({
  providedIn: 'root'
})
export class BlogService {
  private blogsSubject = new BehaviorSubject<Blog[]>([]);
  private selectedBlogSubject = new BehaviorSubject<Blog | null>(null);

  blogs$: Observable<Blog[]> = this.blogsSubject.asObservable();
  selectedBlog$: Observable<Blog | null> = this.selectedBlogSubject.asObservable();

  get blogs(): Blog[] {
    return this.blogsSubject.getValue();
  }

  get selectedBlog(): Blog | null {
    return this.selectedBlogSubject.getValue();
  }

  addBlog(blog: Blog): void {
    const currentBlogs = this.blogsSubject.getValue();
    this.blogsSubject.next([...currentBlogs, blog]);
  }

  setSelectedBlog(blog: Blog | null): void {
    this.selectedBlogSubject.next(blog);
  }

  isTitleDuplicate(title: string): boolean {
    return this.blogsSubject.getValue().some(blog => blog.title === title);
  }
}
