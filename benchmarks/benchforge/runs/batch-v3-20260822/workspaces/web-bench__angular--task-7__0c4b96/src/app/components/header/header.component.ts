import { Component, inject } from '@angular/core';
import { BlogService } from '../../services/blog.service';

@Component({
  selector: 'app-header',
  standalone: true,
  template: `
    <header>
      <h1>Hello Blog <span class="blog-list-len">({{ blogService.blogs().length }})</span></h1>
    </header>
  `,
})
export class HeaderComponent {
  blogService = inject(BlogService);
}
