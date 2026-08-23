import { formatErrorWithContext, formatDraftScriptError } from '../error-formatter';
import { getSourceContextFromContent } from '../source-context';

describe('Error Formatter', () => {
  describe('formatErrorWithContext', () => {
    test('should format basic error without context when no script content provided', () => {
      const error = new Error('Test error');
      const result = formatErrorWithContext(error);
      
      expect(result.message).toBe('Test error');
      expect(result.hasContext).toBe(false);
      expect(result.context).toBeNull();
    });

    test('should format error with context when script content and line number provided', () => {
      const error = new Error('Test error');
      const scriptContent = `function test() {
  console.log('hello');
  throw new Error('test');
  console.log('world');
}`;
      
      const result = formatErrorWithContext(error, {
        scriptContent,
        errorLineNumber: 3,
        fileName: 'test.js'
      });
      
      expect(result.message).toBe('Test error');
      expect(result.hasContext).toBe(true);
      expect(result.context).toBeDefined();
      expect(result.context.errorLine.lineNumber).toBe(3);
      expect(result.context.errorLine.content.trim()).toBe("  throw new Error('test');");
      expect(result.context.contextLines.length).toBeGreaterThan(0);
    });

    test('should handle invalid line numbers gracefully', () => {
      const error = new Error('Test error');
      const scriptContent = 'console.log("hello");';
      
      const result = formatErrorWithContext(error, {
        scriptContent,
        errorLineNumber: 100, // Invalid line number
        fileName: 'test.js'
      });
      
      expect(result.hasContext).toBe(false);
      expect(result.context).toBeNull();
    });
  });

  describe('formatDraftScriptError', () => {
    test('should format draft script error with draft-specific metadata', () => {
      const error = new Error('Draft error');
      const draftContent = `// Pre-request script
const headers = request.headers;
headers['X-Test'] = 'value';
`;
      
      const result = formatDraftScriptError(error, draftContent, 3, 'pre-request');
      
      expect(result.isDraft).toBe(true);
      expect(result.scriptType).toBe('pre-request');
      expect(result.hasContext).toBe(true);
      expect(result.context.errorLine.lineNumber).toBe(3);
      expect(result.context.errorLine.content.trim()).toBe("headers['X-Test'] = 'value';");
    });
  });

  describe('getSourceContextFromContent', () => {
    test('should extract context lines correctly', () => {
      const content = `line 1
line 2
line 3
line 4
line 5`;
      
      const result = getSourceContextFromContent(content, 3, 1);
      
      expect(result.hasContext).toBe(true);
      expect(result.contextLines.length).toBe(3); // line 2, 3, 4
      expect(result.contextLines[0].lineNumber).toBe(2);
      expect(result.contextLines[1].lineNumber).toBe(3);
      expect(result.contextLines[2].lineNumber).toBe(4);
      expect(result.contextLines[1].isErrorLine).toBe(true);
    });

    test('should handle edge cases (first and last lines)', () => {
      const content = `line 1
line 2
line 3`;
      
      // Test first line
      let result = getSourceContextFromContent(content, 1, 2);
      expect(result.contextLines.length).toBe(3); // lines 1, 2, 3
      
      // Test last line
      result = getSourceContextFromContent(content, 3, 2);
      expect(result.contextLines.length).toBe(3); // lines 1, 2, 3
    });
  });
});