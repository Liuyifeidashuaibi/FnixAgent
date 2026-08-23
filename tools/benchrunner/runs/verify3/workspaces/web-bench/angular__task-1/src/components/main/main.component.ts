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

import { Component, inject, Input, ViewChild } from '@angular/core'
import { BlogComponent } from '../blog/blog.component'
import { BlogListComponent } from '../blog-list/blog-list.component'
import { BlogService } from '../../services/blog.service'
import { AsyncPipe, NgIf } from '@angular/common'
import { CommentsComponent } from '../comments/comments.component'

@Component({
  selector: 'app-main',
  standalone: true,
  imports: [BlogComponent, BlogListComponent, AsyncPipe, NgIf, CommentsComponent],
  template: `
    <main class="main">
      <app-blog-list
        [blogs]="(blogService.blogs$ | async) || []"
        [selectedTitle]="(blogService.selectedBlog$ | async)?.title || ''"
        [searchKeyword]="searchKeyword"
        (select)="onSelectBlog($event)"
      />
      <div class="main-right" *ngIf="(blogService.selectedBlog$ | async)?.title">
        <app-blog
          [title]="(blogService.selectedBlog$ | async)?.title || ''"
          [detail]="(blogService.selectedBlog$ | async)?.detail || ''"
        >
        </app-blog>
        <app-comments
          #comments
          [blogTitle]="(blogService.selectedBlog$ | async)?.title || ''"
        ></app-comments>
      </div>
    </main>
  `,
  styles: `
    .main {
      flex: 1;
      padding: 1rem;
      display: flex;
      flex-direction: row;
      gap: 2rem;
    }

   .main-right {
     flex: 1;
   }
  `,
})
export class MainComponent {
  @Input() searchKeyword = ''

  @ViewChild('comments') comments!: CommentsComponent

  blogService = inject(BlogService)

  onSelectBlog(blog: { title: string; detail: string }) {
    this.blogService.selectBlog(blog)
  }

  onFastComment() {
    this.comments.fastComment()
  }
}
