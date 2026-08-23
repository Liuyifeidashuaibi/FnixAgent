import { Component, Output, EventEmitter } from '@angular/core';
import { BlogService } from '../blog.service';
import { Blog } from '../blog.model';

@Component({
  selector: 'app-blog-form',
  template: `
    <div class="modal">
      <div class="modal-content">
        <span class="close-btn" (click)="closeForm()">&times;</span>
        <h2>Create Blog</h2>
        <form (ngSubmit)="submitForm()">
          <label for="title">Title:</label>
          <input type="text" id="title" [(ngModel)]="newBlog.title" name="title" required />

          <label for="content">Content:</label>
          <textarea id="content" [(ngModel)]="newBlog.content" name="content" required></textarea>

          <button type="submit">Create</button>
          <button type="button" (click)="closeForm()">Cancel</button>
        </form>
      </div>
    </div>
  `,
  styles: [`.modal {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    justify-content: center;
    align-items: center;
  }

  .modal-content {
    background-color: white;
    padding: 20px;
    border-radius: 8px;
    width: 400px;
    position: relative;
  }

  .close-btn {
    position: absolute;
    top: 10px;
    right: 10px;
    font-size: 24px;
    cursor: pointer;
  }

  label {
    display: block;
    margin-top: 10px;
  }

  input, textarea {
    width: 100%;
    padding: 8px;
    margin-top: 5px;
    box-sizing: border-box;
  }

  button {
    margin-top: 15px;
    padding: 10px 15px;
    margin-right: 10px;
  }`]
})
export class BlogFormComponent {
  newBlog: Blog = {
    id: '',
    title: '',
    excerpt: '',
    content: '',
    date: new Date().toISOString().split('T')[0],
    category: ''
  };

  @Output() formSubmitted = new EventEmitter<void>();

  constructor(private blogService: BlogService) {}

  submitForm() {
    // Check for duplicate title
    const existingBlog = this.blogService.getBlogs().find(
      blog => blog.title === this.newBlog.title
    );

    if (existingBlog) {
      alert('A blog with this title already exists. Please choose a different title.');
      return;
    }

    // Add the new blog to the service
    this.blogService.addBlog(this.newBlog);
    this.formSubmitted.emit();
    this.closeForm();
  }

  closeForm() {
    // Logic to hide the form
  }
}