import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Comment } from '../models/comment.model';

@Injectable({
  providedIn: 'root'
})
export class CommentService {
  private comments: Comment[] = [];
  private commentsSubject = new BehaviorSubject<Comment[]>([]);
  private nextId = 1;

  comments$: Observable<Comment[]> = this.commentsSubject.asObservable();

  getCommentsForBlog(blogId: number): Comment[] {
    return this.comments.filter(c => c.blogId === blogId);
  }

  getCommentsObservableForBlog(blogId: number): Observable<Comment[]> {
    return new Observable<Comment[]>(observer => {
      observer.next(this.getCommentsForBlog(blogId));
      const sub = this.comments$.subscribe(comments => {
        observer.next(comments.filter(c => c.blogId === blogId));
      });
      return { unsubscribe: () => sub.unsubscribe() };
    });
  }

  addComment(blogId: number, text: string): Comment {
    const comment: Comment = {
      id: this.nextId++,
      blogId,
      text,
      createdAt: new Date()
    };
    this.comments.push(comment);
    this.commentsSubject.next([...this.comments]);
    return comment;
  }

  clearCommentsForBlog(blogId: number): void {
    this.comments = this.comments.filter(c => c.blogId !== blogId);
    this.commentsSubject.next([...this.comments]);
  }

  getAllComments(): Comment[] {
    return [...this.comments];
  }
}
