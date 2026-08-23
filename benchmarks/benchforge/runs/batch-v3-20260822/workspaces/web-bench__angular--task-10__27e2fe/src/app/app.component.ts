import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SearchComponent } from './search.component';
import { BlogListComponent } from './blog-list.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, SearchComponent, BlogListComponent],
  template: `
    <app-search (search)="onSearch($event)"></app-search>
    <app-blog-list [filter]="filter"></app-blog-list>
  `,
  styles: []
})
export class AppComponent {
  filter: string = '';

  onSearch(term: string): void {
    this.filter = term;
  }
}
