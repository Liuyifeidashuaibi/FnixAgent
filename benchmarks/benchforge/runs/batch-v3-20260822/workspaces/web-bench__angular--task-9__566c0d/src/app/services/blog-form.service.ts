import { Injectable } from '@angular/core';
import { Blog } from '../models/blog.model';

@Injectable({
  providedIn: 'root'
})
export class BlogFormService {
  private _visible = false;
  private _editing = false;
  private _selectedBlog: Blog | null = null;

  get visible(): boolean {
    return this._visible;
  }

  get editing(): boolean {
    return this._editing;
  }

  get selectedBlog(): Blog | null {
    return this._selectedBlog;
  }

  get formTitle(): string {
    return this._editing ? 'Edit Form' : 'Create Blog';
  }

  showForCreate(): void {
    this._visible = true;
    this._editing = false;
    this._selectedBlog = null;
  }

  showForEdit(blog: Blog): void {
    this._visible = true;
    this._editing = true;
    this._selectedBlog = { ...blog };
  }

  hide(): void {
    this._visible = false;
    this._editing = false;
    this._selectedBlog = null;
  }

  toggle(): void {
    this._visible = !this._visible;
  }
}
