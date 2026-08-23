// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// 
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
// 
//     http://www.apache.org/licenses/LICENSE-2.0
// 
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { Component, Output, EventEmitter, inject } from '@angular/core'
import { FormsModule } from '@angular/forms'
import { NgIf } from '@angular/common'
import { BlogService } from '../../services/blog.service'
import { Subscription } from 'rxjs'

@Component({
  selector: 'app-blog-form',
  standalone: true,
  imports: [FormsModule, NgIf],
  template: `
    <div class="modal" [class.visible]="visible">
      <div class="modal-content">
        <span class="visible-count">{{ visibleCount }}</span>
        <button class="close-btn" (click)="onClose()">×</button>
        <h2>{{ isEditing ? 'Edit Blog' : 'Create Blog' }}</h2>
        <form class="form" (submit)="onSubmit($event)">
          <div class="form-group">
            <label for="title">Title:</label>
            <input
              id="title"
              type="text"
              [(ngModel)]="title"
              name="title"
              required
              (ngModelChange)="onTitleChange()"
            />
            <span *ngIf="titleExists" class="error">Title already exists!</span>
          </div>
          <div class="form-group">
            <label for="detail">Detail:</label>
            <textarea id="detail" [(ngModel)]="detail" name="detail" required></textarea>
          </div>
          <button type="submit" class="submit-btn" [disabled]="titleExists">
            {{ isEditing ? 'Update' : 'Create' }}
          </button>
        </form>
      </div>
    </div>
  `,
  styles: `
    .modal {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0,0,0,0.5);
      display: none;
      justify-content: center;
      align-items: center;
      z-index: 1000;
    }
    
    .modal.visible {
      display: flex;
    }

    .modal-content {
      background: white;
      padding: 2rem;
      border-radius: 8px;
      position: relative;
      width: 400px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }

    .close-btn {
      position: absolute;
      top: 10px;
      right: 10px;
      border: none;
      background: none;
      font-size: 24px;
      cursor: pointer;
      color: #666;
    }

    .close-btn:hover {
      color: #333;
    }

    .visible-count {
      position: absolute;
      top: 10px;
      left: 10px;
      color: #666;
    }

    h2 {
      margin-top: 0;
      color: #333;
    }

    .form-group {
      margin-bottom: 1rem;
    }

    label {
      display: block;
      margin-bottom: 0.5rem;
      color: #555;
    }

    input, textarea {
      width: 100%;
      padding: 0.5rem;
      border: 1px solid #ddd;
      border-radius: 4px;
      box-sizing: border-box;
    }

    textarea {
      height: 100px;
      resize: vertical;
    }

    .submit-btn {
      background: #4CAF50;
      color: white;
      border: none;
      padding: 0.5rem 1rem;
      border-radius: 4px;
      cursor: pointer;
      width: 100%;
    }

    .submit-btn:disabled {
      background: #cccccc;
      cursor: not-allowed;
    }

    .submit-btn:hover:not(:disabled) {
      background: #45a049;
    }

    .error {
      color: red;
      font-size: 0.8rem;
      margin-top: 0.2rem;
    }
  `,
})
export class BlogFormComponent {
  private blogService = inject(BlogService)

  subscription = new Subscription()

  ngOnInit() {
    this.subscription.add(
      this.blogService.editingBlog$.subscribe((blog) => {
        if (blog) {
          this.showEdit(blog)
        } else {
          this.hide()
        }
      })
    )
  }

  ngOnDestroy() {
    this.subscription.unsubscribe()
  }

  visible = false
  title = ''
  detail = ''
  visibleCount = 0
  titleExists = false
  isEditing = false
  originalTitle = ''

  @Output() close = new EventEmitter<void>()

  show() {
    this.visible = true
    this.visibleCount++
    this.isEditing = false
  }

  showEdit(blog: { title: string; detail: string }) {
    this.visible = true
    this.visibleCount++
    this.isEditing = true
    this.title = blog.title
    this.detail = blog.detail
    this.originalTitle = blog.title
  }

  hide() {
    this.visible = false
    this.title = ''
    this.detail = ''
    this.titleExists = false
    this.isEditing = false
    this.originalTitle = ''
  }

  onClose() {
    this.hide()
    this.close.emit()
  }

  onTitleChange() {
    let blogs = this.blogService.getBlogs()

    if (this.isEditing) {
      blogs = blogs.filter((blog) => blog.title !== this.originalTitle)
    }

    this.titleExists = blogs.some((blog) => blog.title === this.title)
  }

  onSubmit(event: Event) {
    event.preventDefault()
    if (this.title && this.detail) {
      if (this.isEditing) {
        this.blogService.updateBlog(this.originalTitle, { title: this.title, detail: this.detail })
      } else if (!this.titleExists) {
        this.blogService.addBlog({ title: this.title, detail: this.detail })
      }
      this.hide()
    }
  }
}
