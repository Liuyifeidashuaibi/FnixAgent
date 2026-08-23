import { WebSocketRequest, createWebSocketRequest, createWebSocketMessage } from '@/models/websocket-message';
import { serializeToBru, serializeToYaml, deserializeFromBru } from '@/utils/websocket-serializer';

// Test cases for multi-message WebSocket functionality
describe('WebSocket Multi-Message Support', () => {
  test('should create request with multiple messages', () => {
    const request = createWebSocketRequest();
    
    // Add multiple messages
    const message1 = createWebSocketMessage('First Message');
    const message2 = createWebSocketMessage('Second Message');
    const message3 = createWebSocketMessage('Third Message');
    
    const updatedRequest: WebSocketRequest = {
      ...request,
      messages: [message1, message2, message3]
    };
    
    expect(updatedRequest.messages.length).toBe(3);
    expect(updatedRequest.messages[0].name).toBe('First Message');
    expect(updatedRequest.messages[1].name).toBe('Second Message');
    expect(updatedRequest.messages[2].name).toBe('Third Message');
  });

  test('should serialize multi-message request to BRU format', () => {
    const request: WebSocketRequest = {
      id: 'test-id',
      name: 'Test Request',
      url: 'wss://example.com',
      messages: [
        {
          id: 'msg1',
          name: 'Hello Message',
          type: 'text',
          content: 'Hello, World!',
          timestamp: Date.now()
        },
        {
          id: 'msg2',
          name: 'Binary Message',
          type: 'binary',
          content: 'base64data==',
          timestamp: Date.now()
        }
      ],
      headers: {
        'Authorization': 'Bearer token'
      }
    };
    
    const bruContent = serializeToBru(request);
    
    expect(bruContent).toContain('url: wss://example.com');
    expect(bruContent).toContain('Authorization: Bearer token');
    expect(bruContent).toContain('messages:');
    expect(bruContent).toContain('- name: Hello Message');
    expect(bruContent).toContain('- name: Binary Message');
    expect(bruContent).toContain('type: text');
    expect(bruContent).toContain('type: binary');
  });

  test('should serialize multi-message request to YAML format', () => {
    const request: WebSocketRequest = {
      id: 'test-id',
      name: 'Test Request',
      url: 'wss://example.com',
      messages: [
        {
          id: 'msg1',
          name: 'Hello Message',
          type: 'text',
          content: 'Hello, World!',
          timestamp: Date.now()
        }
      ],
      headers: {
        'Content-Type': 'application/json'
      }
    };
    
    const yamlContent = serializeToYaml(request);
    
    expect(yamlContent).toContain('url: wss://example.com');
    expect(yamlContent).toContain('Content-Type: application/json');
    expect(yamlContent).toContain('messages:');
    expect(yamlContent).toContain('- name: Hello Message');
  });

  test('should deserialize multi-message BRU content correctly', () => {
    const bruContent = `url: wss://example.com
headers:
  Authorization: Bearer token
messages:
  - name: First Message
    type: text
    content: |
      Hello, World!
  - name: Second Message
    type: binary
    content: |
      base64data==`;
    
    const request = deserializeFromBru(bruContent);
    
    expect(request.url).toBe('wss://example.com');
    expect(request.headers?.['Authorization']).toBe('Bearer token');
    expect(request.messages.length).toBe(2);
    expect(request.messages[0].name).toBe('First Message');
    expect(request.messages[0].type).toBe('text');
    expect(request.messages[0].content).toBe('Hello, World!');
    expect(request.messages[1].name).toBe('Second Message');
    expect(request.messages[1].type).toBe('binary');
    expect(request.messages[1].content).toBe('base64data==');
  });

  test('should handle backward compatibility with single-message format', () => {
    const oldBruContent = `url: wss://example.com
headers:
  Authorization: Bearer token
message:
  type: text
  content: |
    Hello, World!`;
    
    const request = deserializeFromBru(oldBruContent);
    
    expect(request.messages.length).toBe(1);
    expect(request.messages[0].type).toBe('text');
    expect(request.messages[0].content).toBe('Hello, World!');
  });
});