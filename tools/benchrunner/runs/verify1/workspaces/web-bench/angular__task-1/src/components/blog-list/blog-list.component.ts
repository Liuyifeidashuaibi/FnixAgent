// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// 
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
// 
//     http://www.apache.org/licenses/LICENSE-2.0
// 
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import {
  Component,
  Input,
  Output,
  EventEmitter,
  Pipe,
  PipeTransform,
  ViewChild,
  ElementRef,
  HostListener,
  SimpleChanges,
} from '@angular/core'
import { NgFor } from '@angular/common'
import { TruncateDirective } from '../../directives/truncate.directive'

@Pipe({
  name: 'filterBlogs',
  standalone: true,
})
export class FilterBlogsPipe implements PipeTransform {
  transform(
    blogs: Array<{ title: string; detail: string }>,
    searchText: string
  ): Array<{ title: string; detail: string }> {
    if (!searchText) return blogs

    return blogs.filter(
      (blog) =>
        blog.title.toLowerCase().includes(searchText.toLowerCase()) ||
        blog.detail.toLowerCase().includes(searchText.toLowerCase())
    )
  }
}

@Component({
  selector: 'app-blog-list',
  standalone: true,
  imports: [NgFor, TruncateDirective],
  template: `
    <div class="list" #listContainer (scroll)="onScroll()">
      <div class="list-content" [style.height.px]="totalHeight">
        <div
          class="list-item"
          *ngFor="let blog of visibleBlogs"
          [style.transform]="'translateY(' + blog.offset + 'px)'"
          [class.selected]="selectedTitle === blog.title"
          (click)="onSelect(blog)"
        >
          <span [truncate]="blog.title"></span>
        </div>
      </div>
    </div>
  `,
  styles: `
    .list {
      width: 300px;
      height: 400px;
      border-right: 1px solid #eee;
      background: white;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
      border-radius: 4px;
      overflow-y: auto;
      position: relative;
    }

    .list-content {
      position: relative;
    }

    .list-item {
      height: 40px;
      box-sizing: border-box;
      padding: 8px 16px;
      border-bottom: 1px solid #eee;
      cursor: pointer;
      transition: background-color 0.2s ease, color 0.2s ease;
      display: flex;
      align-items: center;
      font-size: 15px;
      color: #444;
      position: absolute;
      width: 100%;
      left: 0;
    }

    .list-item:hover {
      background-color: #f5f5f5;
    }

    .list-item.selected {
      background-color: #e8f5e9;
      color: #2e7d32;
      font-weight: 500;
      border-left: 4px solid #4CAF50;
    }
  `,
})
export class BlogListComponent {
  @Input() blogs: Array<{ title: string; detail: string }> = []
  @Input() selectedTitle: string = ''
  @Input() searchKeyword: string = ''
  @Output() select = new EventEmitter<{ title: string; detail: string }>()
  @ViewChild('listContainer') listContainer!: ElementRef

  private itemHeight = 40
  private bufferSize = 5
  visibleBlogs: Array<{ title: string; detail: string; offset: number }> = []
  totalHeight = 0
  startIndex = 0

  ngAfterViewInit() {
    this.updateVisibleItems()
  }

  @HostListener('window:resize')
  onResize() {
    this.updateVisibleItems()
  }

  ngOnChanges(changes: SimpleChanges) {
    if (changes['blogs'] || changes['searchKeyword']) {
      this.updateVisibleItems()

      if (changes['searchKeyword'] && this.listContainer) {
        this.listContainer.nativeElement.scrollTop = 0
      }
    }
  }

  onScroll() {
    this.updateVisibleItems()
  }

  private updateVisibleItems() {
    if (!this.listContainer) return

    const container = this.listContainer.nativeElement
    const scrollTop = container.scrollTop
    const viewportHeight = container.clientHeight

    const filteredBlogs = this.getFilteredBlogs()
    this.totalHeight = filteredBlogs.length * this.itemHeight

    const startIndex = Math.max(0, Math.floor(scrollTop / this.itemHeight) - this.bufferSize)
    const endIndex = Math.min(
      filteredBlogs.length,
      Math.ceil((scrollTop + viewportHeight) / this.itemHeight) + this.bufferSize
    )

    this.visibleBlogs = filteredBlogs.slice(startIndex, endIndex).map((blog, index) => ({
      ...blog,
      offset: (startIndex + index) * this.itemHeight,
    }))
  }

  private getFilteredBlogs() {
    if (!this.searchKeyword) return this.blogs

    return this.blogs.filter((blog) =>
      blog.title.toLowerCase().includes(this.searchKeyword.toLowerCase())
    )
  }

  onSelect(blog: { title: string; detail: string }) {
    this.select.emit(blog)
  }
}