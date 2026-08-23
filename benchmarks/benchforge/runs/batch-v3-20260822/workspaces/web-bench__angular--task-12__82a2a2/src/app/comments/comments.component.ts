import { Component, OnInit, OnDestroy, Input } from '@angular/core';
import { CommentService } from '../services/comment.service';
import { Comment } from '../models/comment.model';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-comments',
  template: `
    <div class="comments-section">
      <h2 class="comments-title">Comments</h2>
      
      <div class="comments-list">
        <div *ngFor="let comment of comments" class="comment-item">
          <p class="comment-text">{{ comment.text }}</p>
          <span class="comment-date">{{ comment.date | date:'medium' }}</span>
        </div>
        <p *ngIf="comments.length === 0" class="no-comments">No comments yet. Be the first to comment!</p>
      </div>

      <div class="comment-form">
        <textarea 
          [(ngModel)]="newComment" 
          placeholder="Enter Your Comment"
          rows="4"
          class="comment-textarea">
        </textarea>
        <button (click)="submitComment()" class="comment-btn">Submit</button>
      </div>
    </div>
  `,
  styles: [`
    .comments-section {
      margin-top: 30px;
      padding: 20px;
      background: #f9f9f9;
      border-radius: 8px;
    }
    .comments-title {
      font-size: 24px;
      font-weight: bold;
      margin-bottom: 20px;
      color: #333;
    }
    .comments-list {
      margin-bottom: 20px;
    }
    .comment-item {
      background: white;
      padding: 15px;
      margin-bottom: 10px;
      border-radius: 6px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .comment-text {
      margin: 0 0 8px 0;
      color: #333;
    }
    .comment-date {
      font-size: 12px;
      color: #888;
    }
    .no-comments {
      color: #999;
      text-align: center;
      padding: 20px;
    }
    .comment-form {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .comment-textarea {
      padding: 12px;
      border: 1px solid #ddd;
      border-radius: 6px;
      resize: vertical;
      font-size: 14px;
    }
    .comment-btn {
      padding: 10px 20px;
      background: #007bff;
      color: white;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      align-self: flex-end;
    }
    .comment-btn:hover {
      background: #0056b3;
    }
  `]
})
export class CommentsComponent implements OnInit, OnDestroy {
  @Input() blogId!: number;
  comments: Comment[] = [];
  newComment: string = '';
  private subscription: Subscription | undefined;

  constructor(private commentService: CommentService) {}

  ngOnInit(): void {
    this.subscription = this.commentService.getCommentsByBlogId(this.blogId).subscribe(comments => {
      this.comments = comments;
    });
  }

  ngOnDestroy(): void {
    if (this.subscription) {
      this.subscription.unsubscribe();
    }
  }

  submitComment(): void {
    if (this.newComment.trim()) {
      this.commentService.addComment(this.blogId, this.newComment.trim());
      this.newComment = '';
    }
  }
}
