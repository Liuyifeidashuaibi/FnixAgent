import { Component, Input, Output, EventEmitter } from '@angular/core';

@Component({
  selector: 'app-search',
  templateUrl: './search.component.html',
  styleUrls: ['./search.component.css']
})
export class SearchComponent {
  @Input() blogs: any[] = [];
  @Output() filteredBlogs = new EventEmitter<any[]>();
  
  searchTerm: string = '';
  
  onSearch() {
    if (!this.searchTerm.trim()) {
      this.filteredBlogs.emit(this.blogs);
      return;
    }
    
    const term = this.searchTerm.toLowerCase();
    const filtered = this.blogs.filter(blog => 
      blog.title.toLowerCase().includes(term) || 
      blog.detail.toLowerCase().includes(term)
    );
    
    this.filteredBlogs.emit(filtered);
  }
}