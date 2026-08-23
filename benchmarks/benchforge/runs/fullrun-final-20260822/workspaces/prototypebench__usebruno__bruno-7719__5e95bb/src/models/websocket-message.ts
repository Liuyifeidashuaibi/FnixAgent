export interface WebSocketMessage {
  id: string;
  name: string;
  type: 'text' | 'binary';
  content: string;
  timestamp?: number;
}

export interface WebSocketRequest {
  id: string;
  name: string;
  url: string;
  messages: WebSocketMessage[];
  headers?: Record<string, string>;
  enabled?: boolean;
}

// Helper functions
export const createWebSocketMessage = (name: string = 'New Message'): WebSocketMessage => ({
  id: crypto.randomUUID(),
  name,
  type: 'text',
  content: '',
  timestamp: Date.now()
});

export const createWebSocketRequest = (name: string = 'WebSocket Request'): WebSocketRequest => ({
  id: crypto.randomUUID(),
  name,
  url: '',
  messages: [createWebSocketMessage()],
  headers: {}
});