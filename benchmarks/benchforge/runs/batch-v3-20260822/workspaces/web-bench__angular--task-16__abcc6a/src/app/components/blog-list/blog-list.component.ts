import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TruncateTitleDirective } from '../directives/truncate-title.directive';
import { Blog } from '../models/blog.model';
import { BlogService } from '../services/blog.service';

@Component({
  selector: 'app-blog-list',
  standalone: true,
  imports: [CommonModule, TruncateTitleDirective],
  templateUrl: './blog-list.component.html',
  styleUrls: ['./blog-list.component.css']
})
export class BlogListComponent implements OnInit {
  blogs: Blog[] = [];

  constructor(private blogService: BlogService) {}

  ngOnInit(): void {
    this.blogs = this.blogService.getBlogs();
  }
}
