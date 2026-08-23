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

import { Component, Input, inject, ViewChild, ElementRef } from '@angular/core'
import { FormsModule } from '@angular/forms'
import { DatePipe } from '@angular/common'
import { CommentService } from '../../services/comment.service'

@Component({
  selector: 'app-comments',
  standalone: true,
  imports: [FormsModule, DatePipe],
  template: `
    <div class="comments">
      <h3>Comments</h3>

      <div class="comment-list">
        @for(comment of commentService.getCommentsByBlog(blogTitle); track comment.timestamp) {
        <div class="comment-item">
          <p>{{ comment.text }}</p>
          <small>{{ comment.timestamp | date : 'medium' }}</small>
        </div>
        }
      </div>

      <div class="comment-form">
        <textarea
          #commentInput
          [(ngModel)]="newComment"
          placeholder="Enter Your Comment"
          class="comment-input"
        ></textarea>
        <button class="comment-btn" (click)="onSubmitComment()" [disabled]="!newComment.trim()">
          Submit Comment
        </button>
      </div>
    </div>
  `,
  styles: `
    .comments {
      margin-top: 2rem;
      padding: 1rem;
      background: #f9f9f9;
      border-radius: 8px;
    }

    .comment-list {
      margin: 1rem 0;
    }

    .comment-item {
      background: white;
      padding: 1rem;
      margin-bottom: 1rem;
      border-radius: 4px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }

    .comment-item p {
      margin: 0 0 0.5rem 0;
    }

    .comment-item small {
      color: #666;
    }

    .comment-form {
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }

    .comment-input {
      width: 100%;
      min-height: 80px;
      padding: 0.5rem;
      border: 1px solid #ddd;
      border-radius: 4px;
      resize: vertical;
    }

    .comment-btn {
      align-self: flex-end;
      background: #4CAF50;
      color: white;
      border: none;
      padding: 0.5rem 1rem;
      border-radius: 4px;
      cursor: pointer;
    }

    .comment-btn:disabled {
      background: #cccccc;
      cursor: not-allowed;
    }

    .comment-btn:hover:not(:disabled) {
      background: #45a049;
    }
  `,
})
export class CommentsComponent {
  @Input() blogTitle: string = ''
  @ViewChild('commentInput') commentInput!: ElementRef<HTMLTextAreaElement>

  commentService = inject(CommentService)
  newComment: string = ''

  onSubmitComment() {
    console.log('debugger submit', this)
    if (this.newComment.trim()) {
      this.commentService.addComment({
        blogTitle: this.blogTitle,
        text: this.newComment,
        timestamp: Date.now(),
      })
      this.newComment = ''
    }
  }

  fastComment() {
    console.log('debugger', this.commentInput.nativeElement)

    this.commentInput.nativeElement.focus()
    this.newComment = 'Charming Blog!'
  }
}
