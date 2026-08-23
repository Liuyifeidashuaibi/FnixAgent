export const WebSocketConfig = {
  // Default settings for WebSocket multi-message feature
  defaultMessageCount: 1,
  supportedTypes: ['text', 'binary'] as const,
  maxMessageSize: 10 * 1024 * 1024, // 10MB
  
  // UI behavior
  autoExpandNewMessages: true,
  defaultMessageType: 'text' as const,
  
  // File format compatibility
  legacyFormatSupport: true,
  
  // Performance settings
  debounceDelay: 300,
  
  // Validation rules
  validationRules: {
    minLength: 1,
    maxLength: 1000000, // 1MB max content length
    allowedContentTypes: ['text/plain', 'application/json', 'application/octet-stream']
  }
};

export type WebSocketMessageType = typeof WebSocketConfig.supportedTypes[number];