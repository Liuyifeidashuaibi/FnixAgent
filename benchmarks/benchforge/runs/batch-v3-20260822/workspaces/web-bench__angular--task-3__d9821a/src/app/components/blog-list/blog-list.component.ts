import { Component, EventEmitter, Output, OnInit } from '@angular/core';
import { Blog } from '../../models/blog.model';
import { BlogService } from '../../services/blog.service';

@Component({
  selector: 'app-blog-list',
  templateUrl: './blog-list.component.html',
  styleUrls: ['./blog-list.component.css']
})
export class BlogListComponent implements OnInit {
  blogs: Blog[] = [];
  selectedBlogId: string | null = null;

  @Output() blogSelected = new EventEmitter<Blog>();

  constructor(private blogService: BlogService) {}

  ngOnInit(): void {
    this.blogs = this.blogService.getBlogs();
    // Set 'Morning' as default selected blog
    const morningBlog = this.blogs.find(b => b.title.toLowerCase().includes('morning'));
    if (morningBlog) {
      this.selectedBlogId = morningBlog.id;
      this.blogSelected.emit(morningBlog);
    }
  }

  selectBlog(blog: Blog): void {
    this.selectedBlogId = blog.id;
    this.blogSelected.emit(blog);
  }

  isSelected(blog: Blog): boolean {
    return this.selectedBlogId === blog.id;
  }
}
