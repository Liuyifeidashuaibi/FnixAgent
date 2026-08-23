import { Component } from '@angular/core';
import { TooltipDirective } from '../directives/tooltip.directive';

@Component({
  selector: 'app-blog',
  standalone: true,
  imports: [TooltipDirective],
  template: `
    <button appTooltip="Write a New Blog For everyone">Add Blog</button>
  `,
  styles: [
    `
      button {
        padding: 10px 20px;
        font-size: 16px;
        cursor: pointer;
      }
    `,
  ],
})
export class BlogComponent {}
