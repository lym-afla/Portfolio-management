/**
 * Script to help replace console.log statements with our logger utility
 * Run with: node scripts/replace-console-logs.js
 */
const fs = require('fs');
const path = require('path');
// const { execSync } = require('child_process');

// Configure search patterns
const patterns = [
  {
    search: /console\.log\((.*?)\)/g,
    replace: (match, p1, _offset, string, filename) => {
      const moduleName = getModuleNameFromContent(string, filename) || getModuleName(filename);
      return `logger.log('${moduleName}', ${p1})`;
    },
    description: 'console.log',
  },
  {
    search: /console\.error\((.*?)\)/g,
    replace: (match, p1, _offset, string, filename) => {
      const moduleName = getModuleNameFromContent(string, filename) || getModuleName(filename);
      return `logger.error('${moduleName}', ${p1})`;
    },
    description: 'console.error',
  },
  {
    search: /console\.warn\((.*?)\)/g,
    replace: (match, p1, _offset, string, filename) => {
      const moduleName = getModuleNameFromContent(string, filename) || getModuleName(filename);
      return `logger.warn('${moduleName}', ${p1})`;
    },
    description: 'console.warn',
  },
  {
    search: /console\.info\((.*?)\)/g,
    replace: (match, p1, _offset, string, filename) => {
      const moduleName = getModuleNameFromContent(string, filename) || getModuleName(filename);
      return `logger.info('${moduleName}', ${p1})`;
    },
    description: 'console.info',
  },
];

// Files to exclude from processing
const EXCLUDED_FILES = [
  'logger.js',
  'replace-console-logs.js'
];

// Find all JS and Vue files in src directory
function findFiles(dir, fileList = []) {
  const files = fs.readdirSync(dir);
  
  files.forEach(file => {
    const filePath = path.join(dir, file);
    if (fs.statSync(filePath).isDirectory()) {
      if (file !== 'node_modules' && file !== 'dist') {
        findFiles(filePath, fileList);
      }
    } else if ((file.endsWith('.js') || file.endsWith('.vue')) && !isExcluded(file)) {
      fileList.push(filePath);
    }
  });
  
  return fileList;
}

// Check if file should be excluded
function isExcluded(filename) {
  return EXCLUDED_FILES.some(excludedFile => filename.endsWith(excludedFile));
}

// Helper to get module name from file path
function getModuleName(filePath) {
  if (!filePath) return 'Unknown';
  const parts = filePath.split(path.sep);
  // Use file name without extension, or parent directory name if available
  const fileName = path.basename(parts[parts.length - 1], path.extname(parts[parts.length - 1]));
  return fileName.charAt(0).toUpperCase() + fileName.slice(1);
}

// Extract component name from Vue file content
function getModuleNameFromContent(content, filePath) {
  if (filePath.endsWith('.vue')) {
    // Try to extract name from Vue component definition
    const nameMatch = content.match(/name:\s*['"]([^'"]+)['"]/);
    if (nameMatch && nameMatch[1]) {
      return nameMatch[1];
    }
  } else if (filePath.endsWith('.js')) {
    // Try to extract class or function name
    const classMatch = content.match(/class\s+(\w+)/);
    if (classMatch && classMatch[1]) {
      return classMatch[1];
    }
    
    const functionMatch = content.match(/function\s+(\w+)/);
    if (functionMatch && functionMatch[1]) {
      return functionMatch[1];
    }
  }
  
  return null;
}

// Check if logger is imported in the file, if not add import
function ensureLoggerImport(content) {
  if (!content.includes('import logger from')) {
    // Check for multi-line imports
    const multiLineImportRegex = /import\s+{[\s\S]*?}\s+from\s+['"][^'"]+['"]/g;
    const singleLineImportRegex = /import\s+.*?from\s+['"][^'"]+['"];?\n/g;
    
    // Find all import statements
    const multiLineImports = content.match(multiLineImportRegex) || [];
    const singleLineImports = content.match(singleLineImportRegex) || [];
    
    // If we have imports, add logger import after the last one
    if (multiLineImports.length > 0 || singleLineImports.length > 0) {
      // Check if the last import is multi-line or single-line
      const lastMultiLineImport = multiLineImports.length > 0 
        ? multiLineImports[multiLineImports.length - 1] 
        : '';
      const lastSingleLineImport = singleLineImports.length > 0 
        ? singleLineImports[singleLineImports.length - 1] 
        : '';
      
      // Find the position of the last import statement
      const lastMultiLinePos = content.lastIndexOf(lastMultiLineImport) + lastMultiLineImport.length;
      const lastSingleLinePos = content.lastIndexOf(lastSingleLineImport) + lastSingleLineImport.length;
      const lastImportPos = Math.max(lastMultiLinePos, lastSingleLinePos);
      
      // Add logger import after the last import
      return (
        content.slice(0, lastImportPos) +
        "\nimport logger from '@/utils/logger'\n" +
        content.slice(lastImportPos)
      );
    } else {
      // No imports found, add at the top
      return "import logger from '@/utils/logger'\n\n" + content;
    }
  }
  return content;
}

// Process a file to replace console statements
function processFile(filePath) {
  let content = fs.readFileSync(filePath, 'utf-8');
  let hasChanges = false;
  
  // Get file name for logging
  const fileName = path.basename(filePath);
  
  // Skip excluded files
  if (isExcluded(fileName)) {
    console.log(`Skipping excluded file: ${fileName}`);
    return 0;
  }
  
  // Check if file has any console statements to replace
  let needsLogger = false;
  for (const pattern of patterns) {
    if (pattern.search.test(content)) {
      needsLogger = true;
      break;
    }
  }
  
  // Add logger import if needed
  if (needsLogger) {
    const updatedContent = ensureLoggerImport(content);
    if (updatedContent !== content) {
      content = updatedContent;
      hasChanges = true;
    }
    
    // For Vue files, add ESLint disable comment if not already present
    if (filePath.endsWith('.vue') && !content.includes('eslint-disable no-undef')) {
      const scriptTagPos = content.indexOf('<script>');
      if (scriptTagPos !== -1) {
        content = 
          content.slice(0, scriptTagPos + 8) + 
          '\n/* eslint-disable no-undef */\n' +
          content.slice(scriptTagPos + 8);
        hasChanges = true;
      }
    }
  }
  
  // Replace console statements
  for (const pattern of patterns) {
    const newContent = content.replace(pattern.search, (match, ...args) => {
      hasChanges = true;
      // Pass the file content and file path to the replacement function
      return pattern.replace(match, args[0], args[1], content, filePath);
    });
    
    if (newContent !== content) {
      content = newContent;
    }
  }
  
  // Write back if changes were made
  if (hasChanges) {
    fs.writeFileSync(filePath, content, 'utf-8');
    console.log(`Updated: ${filePath}`);
    return 1;
  }
  
  return 0;
}

// Main execution
console.log('Starting to replace console statements with logger...');
const srcDir = path.join(__dirname, '..', 'src');
const files = findFiles(srcDir);
console.log(`Found ${files.length} files to process`);

let replacementCount = 0;
files.forEach(file => {
  replacementCount += processFile(file);
});

console.log(`Done! Updated ${replacementCount} files.`);
console.log('Remember to manually review the changes before committing.');

// Additional tip for searching remaining console statements
console.log('\nTo find any remaining console statements, you can run:');
console.log('grep -r "console\\." src --include="*.js" --include="*.vue" | grep -v "logger.js"'); 