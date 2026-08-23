import { Component, Output, EventEmitter, Input } from '@angular/core';

@Component({
  selector: 'app-blog-form',
  template: `
    <div class="modal">
      <div class="modal-content">
        <span class="close-btn" (click)="close()">&times;</span>
        <h2>{{ mode === 'edit' ? 'Edit Blog' : 'Create Blog' }}</h2>
        <div class="visible-count">{{ visibleCount }}</div>
        <form (ngSubmit)="onSubmit()">
          <label for="title">
            Title:
            <input type="text" [(ngModel)]="blog.title" name="title" required />
          </label>
          <label for="detail">
            Content:
            <textarea [(ngModel)]="blog.content" name="content" required></textarea>
          </label>
          <button type="submit" class="submit-btn">{{ mode === 'edit' ? 'Update' : 'Create' }}</button>
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
    background-color: rgba(0,0,0,0.5);
    display: flex;
    justify-content: center;
    align-items: center;
  }

  .modal-content {
    background-color: white;
    padding: 20px;
    border-radius: 8px;
    width: 300px;
  }

  .close-btn {
    float: right;
    cursor: pointer;
    font-size: 24px;
  }

  h2 {
    margin-top: 0;
  }

  label {
    display: block;
    margin-bottom: 10px;
  }

  input, textarea {
    width: 100%;
    padding: 8px;
    margin-bottom: 10px;
    box-sizing: border-box;
  }

  .submit-btn {
    background-color: #007BFF;
    color: white;
    padding: 10px 15px;
    border: none;
    cursor: pointer;
  }

  .submit-btn:hover {
    background-color: #0056b3;
  }

  .visible-count {
    position: absolute;
    top: 10px;
    left: 10px;
    font-weight: bold;
  }
`]
})
export class BlogFormComponent {
  @Output() blogCreated = new EventEmitter();
  @Output() blogUpdated = new EventEmitter();
  @Input() mode: 'create' | 'edit' = 'create';
  @Input() blog: any = {
    title: '',
    content: ''
  };

  visibleCount = 0;

  onSubmit() {
    if (this.mode === 'edit') {
      this.blogUpdated.emit(this.blog);
    } else {
      this.blogCreated.emit(this.blog);
    }
    this.close();
    this.incrementVisibleCount();
  }

  close() {
    // Logic to hide the modal
  }

  incrementVisibleCount() {
    this.visibleCount += 1;
  }
}
