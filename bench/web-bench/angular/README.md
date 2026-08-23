# Angular Blog App - v19

A simple blog application built with Angular v19 using standalone components.

## Project Structure

```
src/
├── app/
│   ├── blog-list/
│   │   └── blog-list.component.ts    # Displays list of blog titles
│   ├── blog/
│   │   └── blog.component.ts          # Displays blog content
│   ├── main/
│   │   └── main.component.ts          # Main layout with sidebar + content
│   ├── app.component.ts               # Root component
│   └── app.config.ts                  # App configuration
├── main.ts                            # Bootstrap entry point
└── styles.css                         # Global styles
```

## Features

✅ **BlogList Component**
- Accepts array of blogs as `@Input()` property
- Displays titles in div elements with class `list-item`
- Each item has height of 40px with border-box layout

✅ **Main Component**
- Mock blog data: `{title: 'Morning', detail: 'Morning My Friends'}, {title: 'Travel', detail: 'I love traveling!'}`
- Blog-list positioned on left side with width of 300px
- Blog component occupies remaining space
- Displays content from first blog item

✅ **Blog Component**
- Shows blog title and detail
- Uses first item from mock data

## Installation & Running

```bash
# Install dependencies
npm install

# Start development server
npm start

# Build for production
npm run build
```

The app will be available at `http://localhost:4200/`

## Angular Version
- Angular v19.0.0
- Standalone components
- TypeScript 5.6.2