import { Component, EventEmitter, Output } from '@angular/core';

@Component({
  selector: 'app-blog-form',
  templateUrl: './blog-form.component.html',
  styleUrls: ['./blog-form.component.css']
})
export class BlogFormComponent {
  @Output() close = new EventEmitter<void>();

  isVisible = true;

  title = '';
  content = '';

  onClose(): void {
    this.isVisible = false;
    this.close.emit();
  }

  onSubmit(): void {
    console.log('Blog submitted:', { title: this.title, content: this.content });
    this.onClose();
  }
}
