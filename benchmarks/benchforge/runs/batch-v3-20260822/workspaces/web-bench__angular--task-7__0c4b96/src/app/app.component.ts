import { Component, inject } from '@angular/core';
import { BlogService } from './services/blog.service';
import { BlogFormComponent } from './components/blog-form/blog-form.component';
import { BlogListComponent } from './components/blog-list/blog-list.component';
import { HeaderComponent } from './components/header/header.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [HeaderComponent, BlogFormComponent, BlogListComponent],
  template: `
    <app-header></app-header>
    <div class="container">
      <app-blog-form></app-blog-form>
      <app-blog-list></app-blog-list>
    </div>
  `,
  styles: [`
    .container {
      max-width: 800px;
      margin: 0 auto;
      padding: 20px;
    }
  `]
})
export class AppComponent {
  blogService = inject(BlogService);
}
