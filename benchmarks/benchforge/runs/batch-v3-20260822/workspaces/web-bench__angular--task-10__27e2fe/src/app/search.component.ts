import { Component, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-search',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <input
      type="text"
      [(ngModel)]="searchTerm"
      (ngModelChange)="onSearch()"
      placeholder="Search Blogs"
    />
  `,
  styles: [`
    :host {
      display: block;
      width: 200px;
      box-sizing: border-box;
    }
    input {
      width: 100%;
      padding: 8px;
      box-sizing: border-box;
    }
  `]
})
export class SearchComponent {
  searchTerm: string = '';

  @Output() search = new EventEmitter<string>();

  onSearch(): void {
    this.search.emit(this.searchTerm);
  }
}
