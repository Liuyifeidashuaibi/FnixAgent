import { Component } from '@angular/core';

@Component({
  selector: 'app-root',
  template: `
    <app-header></app-header>
    <app-blog-form (blogCreated)="onBlogCreated($event)"></app-blog-form>
  `,
  styles: []
})
export class AppComponent {
  onBlogCreated(blog: any) {
    // Logic to handle the created blog
  }
}