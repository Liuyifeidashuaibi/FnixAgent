import { WebSocketRequest, WebSocketMessage } from '@/models/websocket-message';

/**
 * Serializer for WebSocket requests to BRU format
 */
export const serializeToBru = (request: WebSocketRequest): string => {
  // For backward compatibility, if there's only one message, use the old single-message format
  if (request.messages.length === 1) {
    const message = request.messages[0];
    return `url: ${request.url}
headers:
${Object.entries(request.headers || {}).map(([key, value]) => `  ${key}: ${value}`).join('\n')}
message:
  type: ${message.type}
  content: |
    ${message.content.split('\n').map(line => `    ${line}`).join('\n')}`;
  }
  
  // Multi-message format
  return `url: ${request.url}
headers:
${Object.entries(request.headers || {}).map(([key, value]) => `  ${key}: ${value}`).join('\n')}
messages:
${request.messages.map((message, index) => `  - name: ${message.name}
    type: ${message.type}
    content: |
      ${message.content.split('\n').map(line => `      ${line}`).join('\n')}`).join('\n')}`;
};

/**
 * Serializer for WebSocket requests to YAML format
 */
export const serializeToYaml = (request: WebSocketRequest): string => {
  // For backward compatibility, if there's only one message, use the old single-message format
  if (request.messages.length === 1) {
    const message = request.messages[0];
    return `url: ${request.url}
headers:
${Object.entries(request.headers || {}).map(([key, value]) => `  ${key}: ${value}`).join('\n')}
message:
  type: ${message.type}
  content: |
    ${message.content.split('\n').map(line => `    ${line}`).join('\n')}`;
  }
  
  // Multi-message format
  return `url: ${request.url}
headers:
${Object.entries(request.headers || {}).map(([key, value]) => `  ${key}: ${value}`).join('\n')}
messages:
${request.messages.map((message, index) => `  - name: ${message.name}
    type: ${message.type}
    content: |
      ${message.content.split('\n').map(line => `      ${line}`).join('\n')}`).join('\n')}`;
};

/**
 * Deserialize from BRU/YAML format to WebSocketRequest object
 */
export const deserializeFromBru = (content: string): WebSocketRequest => {
  // Simple parsing logic - in real implementation would use proper YAML parser
  const lines = content.split('\n');
  let url = '';
  const headers: Record<string, string> = {};
  let messages: WebSocketMessage[] = [];
  
  // Parse URL
  const urlMatch = content.match(/^url:\s*(.*)$/m);
  if (urlMatch && urlMatch[1]) {
    url = urlMatch[1].trim();
  }
  
  // Parse headers
  const headersStart = content.indexOf('headers:');
  if (headersStart !== -1) {
    const headersContent = content.substring(headersStart + 8).split('\n').filter(line => line.trim() && line.trim().startsWith('  '));
    headersContent.forEach(line => {
      const match = line.match(/^\s*([^:]+):\s*(.*)$/);
      if (match && match[1] && match[2]) {
        headers[match[1].trim()] = match[2].trim();
      }
    });
  }
  
  // Check for multi-message format (has 'messages:' section)
  const messagesStart = content.indexOf('messages:');
  if (messagesStart !== -1) {
    // Parse multi-message format
    const messagesContent = content.substring(messagesStart + 9);
    const messageBlocks = messagesContent.split(/\s*-\s*name:/).filter(block => block.trim());
    
    if (messageBlocks.length > 0) {
      messages = messageBlocks.map(block => {
        const nameMatch = block.match(/^([^\n]+)/m);
        const name = nameMatch && nameMatch[1] ? nameMatch[1].trim() : 'New Message';
        
        const typeMatch = block.match(/type:\s*([^\n]+)/m);
        const type = typeMatch && typeMatch[1] ? typeMatch[1].trim() as 'text' | 'binary' : 'text';
        
        const contentMatch = block.match(/content:\s*\|\s*([\s\S]*?)(?=\n\s*[-\w]|$)/m);
        const content = contentMatch && contentMatch[1] ? contentMatch[1].replace(/^\s*/gm, '').trim() : '';
        
        return {
          id: crypto.randomUUID(),
          name,
          type,
          content,
          timestamp: Date.now()
        };
      });
    }
  } else {
    // Parse single-message format
    const messageStart = content.indexOf('message:');
    if (messageStart !== -1) {
      const messageContent = content.substring(messageStart + 8);
      const typeMatch = messageContent.match(/type:\s*([^\n]+)/m);
      const type = typeMatch && typeMatch[1] ? typeMatch[1].trim() as 'text' | 'binary' : 'text';
      
      const contentMatch = messageContent.match(/content:\s*\|\s*([\s\S]*?)(?=\n\s*[-\w]|$)/m);
      const content = contentMatch && contentMatch[1] ? contentMatch[1].replace(/^\s*/gm, '').trim() : '';
      
      messages = [{
        id: crypto.randomUUID(),
        name: 'Message',
        type,
        content,
        timestamp: Date.now()
      }];
    }
  }
  
  // If no messages found, create default
  if (messages.length === 0) {
    messages = [{
      id: crypto.randomUUID(),
      name: 'New Message',
      type: 'text',
      content: '',
      timestamp: Date.now()
    }];
  }
  
  return {
    id: crypto.randomUUID(),
    name: 'WebSocket Request',
    url,
    messages,
    headers,
    enabled: true
  };
};