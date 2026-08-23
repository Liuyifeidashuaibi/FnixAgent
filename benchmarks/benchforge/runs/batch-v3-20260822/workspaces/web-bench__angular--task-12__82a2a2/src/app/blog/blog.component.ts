import { Component, OnInit } from '@angular/core';
import { BlogService } from '../services/blog.service';
import { Blog } from '../models/blog.model';

@Component({
  selector: 'app-blog',
  templateUrl: './blog.component.html',
  styleUrls: ['./blog.component.css']
})
export class BlogComponent implements OnInit {
  blogs: Blog[] = [];
  selectedBlog: Blog | null = null;
  isEditing = false;
  editTitle = '';
  editContent = '';

  constructor(private blogService: BlogService) {}

  ngOnInit(): void {
    this.blogs = this.blogService.getBlogs();
  }

  selectBlog(blog: Blog): void {
    this.selectedBlog = blog;
  }

  startEdit(blog: Blog): void {
    this.isEditing = true;
    this.editTitle = blog.title;
    this.editContent = blog.content;
  }

  saveEdit(): void {
    if (this.selectedBlog) {
      this.blogService.updateBlog(this.selectedBlog.id, this.editTitle, this.editContent);
      this.blogs = this.blogService.getBlogs();
      this.selectedBlog = this.blogService.getBlogById(this.selectedBlog.id);
      this.isEditing = false;
    }
  }

  cancelEdit(): void {
    this.isEditing = false;
  }

  deleteBlog(blog: Blog): void {
    this.blogService.deleteBlog(blog.id);
    this.blogs = this.blogService.getBlogs();
    if (this.selectedBlog && this.selectedBlog.id === blog.id) {
      this.selectedBlog = null;
    }
  }

  addBlog(): void {
    const newBlog = this.blogService.addBlog('New Blog', 'New content');
    this.blogs = this.blogService.getBlogs();
    this.selectBlog(newBlog);
  }
}
