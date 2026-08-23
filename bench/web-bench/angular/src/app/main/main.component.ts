import { Component, OnInit } from '@angular/core';

@Component({
  selector: 'app-main',
  template: `
    <div style='display: flex; height: 100vh;'>
      <div style='width: 200px; box-sizing: border-box;'>
        <app-search [blogs]='blogs' (filteredBlogs)='onBlogsFiltered($event)'></app-search>
      </div>
      <app-blog-list [blogs]='filteredBlogs' (selectedBlogChange)='onBlogSelected($event)' style='width: 300px; border-box: border-box;'></app-blog-list>
      <app-blog [blog]='selectedBlog' style='flex: 1; border-box: border-box;'></app-blog>
    </div>
  `
})
export class MainComponent implements OnInit {
  blogs = [{ title: 'Morning', detail: 'Morning My Friends' }, { title: 'Travel', detail: 'I love traveling!' }];
  filteredBlogs = this.blogs;
  selectedBlog = this.blogs[0];

  onBlogSelected(blog: any) {
    this.selectedBlog = blog;
  }

  onBlogsFiltered(filtered: any[]) {
    this.filteredBlogs = filtered;
  }

  ngOnInit() {
    // Initialize with all blogs
    this.filteredBlogs = this.blogs;
  }
}