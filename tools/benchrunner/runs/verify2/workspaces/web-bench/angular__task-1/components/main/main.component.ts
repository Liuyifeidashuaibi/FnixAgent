import { Component } from '@angular/core';

@Component({
  selector: 'app-main',
  template: `<div class="main-content">
              <p>This is the main content area.</p>
            </div>`,
  styles: [`.main-content {
    padding: 20px;
    text-align: left;
    flex: 1;
    display: flex;
    align-items: flex-start;
    justify-content: flex-start;
  }`]
})
export class MainComponent { }
