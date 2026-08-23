import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';

import { AppComponent } from './app.component';
import { BlogListComponent } from './components/blog-list/blog-list.component';
import { TruncateTitleDirective } from './directives/truncate-title.directive';

@NgModule({
  declarations: [
    AppComponent,
    BlogListComponent,
    TruncateTitleDirective
  ],
  imports: [
    BrowserModule
  ],
  providers: [],
  bootstrap: [AppComponent]
})
export class AppModule { }
