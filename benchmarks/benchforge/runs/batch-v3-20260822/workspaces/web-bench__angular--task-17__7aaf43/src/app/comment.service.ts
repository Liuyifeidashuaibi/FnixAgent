import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class CommentService {
  private fastCommentSource = new Subject<void>();
  fastComment$ = this.fastCommentSource.asObservable();

  triggerFastComment(): void {
    this.fastCommentSource.next();
  }
}
