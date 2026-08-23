/*
 * Bruno Request Body Handler Tests
 * Tests for BRU-3153 - Stream-backed request body handling
 */

import { StreamAwareRequestBodyHandler } from '../src/request-body-handler';

const handler = new StreamAwareRequestBodyHandler();

describe('StreamAwareRequestBodyHandler', () => {
  describe('processRequestBody', () => {
    it('should preserve Buffer data without modification', async () => {
      const buffer = Buffer.from('test binary data');
      const variables = { test: 'value' };
      
      const result = await handler.processRequestBody(buffer, variables);
      
      expect(result).toBe(buffer);
      expect(result.equals(buffer)).toBe(true);
    });
    
    it('should preserve stream-like objects without modification', async () => {
      // Mock stream-like object
      const streamLike = {
        pipe: jest.fn(),
        readable: true
      };
      
      const variables = { test: 'value' };
      
      const result = await handler.processRequestBody(streamLike, variables);
      
      expect(result).toBe(streamLike);
    });
    
    it('should interpolate variables in text-based bodies', async () => {
      const textBody = 'Hello {{test}} world';
      const variables = { test: 'Bruno' };
      
      const result = await handler.processRequestBody(textBody, variables);
      
      expect(result).toBe('Hello Bruno world');
    });
    
    it('should handle JSON string bodies correctly', async () => {
      const jsonBody = '{"message": "{{test}}"}';
      const variables = { test: 'success' };
      
      const result = await handler.processRequestBody(jsonBody, variables);
      
      expect(result).toBe('{"message": "success"}');
    });
  });
});