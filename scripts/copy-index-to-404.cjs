const fs = require('fs');
const path = require('path');

const distDir = path.join(__dirname, '..', 'dist');
const indexPath = path.join(distDir, 'index.html');
const fallbackPath = path.join(distDir, '404.html');

try {
  if (!fs.existsSync(distDir)) {
    console.warn('dist directory not found:', distDir);
    process.exit(0);
  }

  if (!fs.existsSync(indexPath)) {
    console.warn('index.html not found in dist, skipping copy.');
    process.exit(0);
  }

  fs.copyFileSync(indexPath, fallbackPath);
  console.log('Copied index.html -> 404.html');
} catch (err) {
  console.error('Failed to copy index to 404:', err);
  process.exit(1);
}
