import { Component, Input, Output, EventEmitter, OnChanges } from '@angular/core';

@Component({
  selector: 'app-blog-form',
  templateUrl: './blog-form.component.html',
  styleUrls: ['./blog-form.component.css']
})
export class BlogFormComponent implements OnChanges {
  @Input() isVisible: boolean = false;
  @Output() close = new EventEmitter<void>();
  
  visibleCount: number = 0;
  private wasVisible: boolean = false;

  ngOnChanges(): void {
    // Increment count when isVisible changes from false to true
    if (this.isVisible && !this.wasVisible) {
      this.visibleCount++;
      this.wasVisible = true;
    } else if (!this.isVisible) {
      this.wasVisible = false;
    }
  }

  closeModal(): void {
    this.close.emit();
  }
}