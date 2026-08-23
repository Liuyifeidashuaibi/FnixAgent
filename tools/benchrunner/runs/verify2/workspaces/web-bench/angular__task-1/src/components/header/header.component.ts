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

import { Component, Output, EventEmitter, Input, inject } from '@angular/core'
import { BlogService } from '../../services/blog.service'
import { TooltipDirective } from '../../directives/tooltip.directive'
import { Router } from '@angular/router'

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [TooltipDirective],
  template: `
    <header class="header">
      <div class="title-container">
        <span>Hello Blog</span>
        <span class="blog-list-len">({{ blogCount }})</span>
      </div>
      <div class="btn-container">
        <button class="add-btn fast-btn" (click)="onFastComment()">Fast Comment</button>
        <button class="add-btn random-btn" (click)="onAddRandomBlogs()">Random Blogs</button>
        <button class="add-btn" (click)="openForm.emit()" tooltip="Write a New Blog For everyone">
          Add Blog
        </button>
        <button class="game-btn" (click)="navigateToGame()">🎮</button>
      </div>
    </header>
  `,
  styles: `
    .header {
      background-color: #4CAF50;
      color: white;
      padding: 1rem;
      text-align: center;
      font-size: 1.5rem;
      font-weight: bold;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .title-container {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .blog-list-len {
      font-size: 1rem;
      opacity: 0.8;
    }

    .btn-container {
      display: flex;
      gap: 1rem;
    }

    .add-btn {
      background: #1976d2;
      color: white;
      border: none;
      padding: 0.5rem 1rem;
      border-radius: 4px;
      cursor: pointer;
      font-size: 1rem;
    }

    .random-btn {
      background: #ff9800;
    }

    .random-btn:hover {
      background: #f57c00;
    }

    .fast-btn {
      background: #9c27b0;
    }

    .fast-btn:hover {
      background: #7b1fa2;
    }

    .add-btn:hover {
      background: #1565c0;
    }

    .game-btn {
      background: #673ab7;
      color: white;
      border: none;
      padding: 0.5rem 1rem;
      border-radius: 4px;
      cursor: pointer;
      font-size: 1.2rem;
    }

    .game-btn:hover {
      background: #5e35b1;
    }
  `,
})
export class HeaderComponent {
  @Input() blogCount = 0
  @Output() openForm = new EventEmitter<void>()
  @Output() fastComment = new EventEmitter<void>()

  private router = inject(Router)

  constructor(private blogService: BlogService) {}

  onAddRandomBlogs() {
    const randomBlogs = Array.from({ length: 100000 }, () => ({
      title: `RandomBlog-${Math.floor(Math.random() * 1000000000000)
        .toString()
        .padStart(12, '0')}`,
      detail: 'This is a random blog post',
    }))

    this.blogService.addRandomBlogs(randomBlogs)
  }

  onFastComment() {
    this.fastComment.emit()
  }

  navigateToGame() {
    this.router.navigate(['/game'])
  }
}