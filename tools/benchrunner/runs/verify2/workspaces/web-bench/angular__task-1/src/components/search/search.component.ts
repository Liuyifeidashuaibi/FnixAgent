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

import { Component, Output, EventEmitter } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-search',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="search">
      <input 
        type="text" 
        [(ngModel)]="searchText"
        (ngModelChange)="onSearch($event)"
        placeholder="Search Blogs"
        class="search-input"
      >
    </div>
  `,
  styles: `
    .search {
      width: 200px;
      box-sizing: border-box;
      padding: 8px;
    }

    .search-input {
      width: 100%;
      padding: 8px;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-size: 14px;
      box-sizing: border-box;
    }

    .search-input:focus {
      outline: none;
      border-color: #4CAF50;
    }
  `
})
export class SearchComponent {
  searchText = '';
  @Output() search = new EventEmitter<string>();

  onSearch(text: string) {
    this.search.emit(text);
  }
}