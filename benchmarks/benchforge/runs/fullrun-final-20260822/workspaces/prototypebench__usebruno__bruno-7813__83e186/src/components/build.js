const fs = require('fs');
const path = require('path');

// Simple build script for components
console.log('Building Bruno components...');

// Copy files to dist directory
const srcDir = path.join(__dirname, '.');
const distDir = path.join(__dirname, '..', '..', 'dist', 'components');

// Ensure dist directory exists
if (!fs.existsSync(distDir)) {
  fs.mkdirSync(distDir, { recursive: true });
}

// Copy component files
const filesToCopy = [
  'SelectionList.tsx',
  'SelectionList.css',
  'SelectionList.d.ts',
  'index.ts'
];

filesToCopy.forEach(file => {
  const srcPath = path.join(srcDir, file);
  const distPath = path.join(distDir, file);
  
  if (fs.existsSync(srcPath)) {
    const content = fs.readFileSync(srcPath, 'utf8');
    fs.writeFileSync(distPath, content);
    console.log(`Copied ${file} to dist`);
  }
});

console.log('Build completed successfully!');
