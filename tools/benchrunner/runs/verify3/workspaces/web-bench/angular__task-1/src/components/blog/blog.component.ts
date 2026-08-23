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

import { Component, Input, inject } from '@angular/core'
import { BlogService } from '../../services/blog.service'
import { CommentService } from '../../services/comment.service'
import { MarkedPipe } from '../../pipes/marked.pipe'
import { TruncateDirective } from '../../directives/truncate.directive'

@Component({
  selector: 'app-blog',
  standalone: true,
  imports: [TruncateDirective, MarkedPipe],
  template: `
    <div class="blog">
      <div class="right-btns">
        <button class="edit-btn" (click)="onEdit()">Edit</button>
        <button class="delete-btn" (click)="onDelete()">Delete</button>
      </div>
      <h2 [truncate]="title" class="blog-title">{{ title }}</h2>
      <div [innerHTML]="detail | marked"></div>
    </div>
  `,
  styles: `
    .blog {
      position: relative;
    }

    .right-btns {
      position: absolute;
      top: 10px;
      right: 10px;
      display: flex;
      gap: 8px;
    }

    .blog-title {
      width: fit-content;
      font-size: 24px;
      margin-bottom: 1rem;
    }

    .delete-btn {
      background: #dc3545;
      color: white;
      border: none;
      padding: 0.5rem 1rem;
      border-radius: 4px;
      cursor: pointer;
    }

    .delete-btn:hover {
      background: #c82333;
    }

    .edit-btn {
      background: #1976d2;
      color: white; 
      border: none;
      padding: 0.5rem 1rem;
      border-radius: 4px;
      cursor: pointer;
    }

    .edit-btn:hover {
      background: #1565c0;
    }

    :host ::ng-deep {
      code {
        background: #f4f4f4;
        padding: 2px 4px;
        border-radius: 4px;
      }

      pre {
        background: #f4f4f4;
        padding: 1rem;
        border-radius: 4px;
        overflow-x: auto;
      }

      ul {
        padding-left: 20px;
      }

      p {
        margin: 1rem 0;
        line-height: 1.5;
      }

      h1, h2, h3 {
        margin: 1.5rem 0 1rem;
      }

      a {
        color: #1976d2;
        text-decoration: none;
      }

      a:hover {
        text-decoration: underline;
      }
    }
  `,
})
export class BlogComponent {
  @Input() title: string = ''
  @Input() detail: string = ''

  blogService = inject(BlogService)
  commentService = inject(CommentService)

  onDelete() {
    if (this.title) {
      this.blogService.deleteBlog({ title: this.title, detail: this.detail })
      this.commentService.deleteBlogComments(this.title)
    }
  }

  onEdit() {
    if (this.title) {
      this.blogService.startEdit({ title: this.title, detail: this.detail })
    }
  }
}
