import { Component } from '@angular/core';

@Component({
  selector: 'app-header',
  template: `<div class="header-container">Hello Blog</div>`,
  styles: [`.header-container {
    background-color: #4CAF50; /* Green background color */
    color: white;
    padding: 20px;
    text-align: center;
    font-size: 24px;
  }`]
})
export class HeaderComponent { }
