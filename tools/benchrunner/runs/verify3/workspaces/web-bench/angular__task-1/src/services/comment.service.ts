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

import { Injectable, inject } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { ToastService } from './toast.service';

export interface Comment {
  blogTitle: string;
  text: string;
  timestamp: number;
}

@Injectable({
  providedIn: 'root'
})
export class CommentService {
  private toastService = inject(ToastService);
  private commentsSubject = new BehaviorSubject<Comment[]>([]);
  comments$ = this.commentsSubject.asObservable();

  addComment(comment: Comment) {
    const currentComments = this.commentsSubject.value;
    this.commentsSubject.next([...currentComments, comment]);
    this.toastService.show('New Comment Created Successfully!');
  }

  getCommentsByBlog(blogTitle: string) {
    return this.commentsSubject.value.filter(comment => comment.blogTitle === blogTitle);
  }

  updateBlogTitle(oldTitle: string, newTitle: string) {
    const currentComments = this.commentsSubject.value;
    const updatedComments = currentComments.map(comment => 
      comment.blogTitle === oldTitle ? {...comment, blogTitle: newTitle} : comment
    );
    this.commentsSubject.next(updatedComments);
  }

  deleteBlogComments(blogTitle: string) {
    const currentComments = this.commentsSubject.value;
    const updatedComments = currentComments.filter(comment => comment.blogTitle !== blogTitle);
    this.commentsSubject.next(updatedComments);
  }
}