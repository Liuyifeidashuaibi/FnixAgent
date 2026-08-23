import { Component, OnInit } from '@angular/core';
import { BlogFormService } from '../../services/blog-form.service';
import { BlogService } from '../../services/blog.service';

@Component({
  selector: 'app-blog-form',
  templateUrl: './blog-form.component.html',
  styleUrls: ['./blog-form.component.css']
})
export class BlogFormComponent implements OnInit {
  title = '';
  content = '';
  author = '';

  constructor(
    private blogFormService: BlogFormService,
    private blogService: BlogService
  ) {}

  ngOnInit(): void {
    this.blogFormService.formState$.subscribe(state => {
      if (state.mode === 'edit' && state.blog) {
        this.title = state.blog.title;
        this.content = state.blog.content;
        this.author = state.blog.author;
      } else {
        this.title = '';
        this.content = '';
        this.author = '';
      }
    });
  }

  onSubmit(): void {
    const state = this.blogFormService.getFormState();
    if (state.mode === 'edit' && state.blog) {
      this.blogService.updateBlog(state.blog.id, {
        title: this.title,
        content: this.content,
        author: this.author,
        date: state.blog.date
      });
    } else {
      this.blogService.addBlog({
        title: this.title,
        content: this.content,
        author: this.author,
        date: new Date().toISOString().split('T')[0]
      });
    }
    this.blogFormService.closeForm();
  }

  onCancel(): void {
    this.blogFormService.closeForm();
  }

  get formTitle(): string {
    return this.blogFormService.getFormState().mode === 'edit' ? 'Edit Form' : 'Create Blog';
  }

  get isVisible(): boolean {
    return this.blogFormService.getFormState().visible;
  }
}
