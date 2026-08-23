import { cancelRequest } from './cancelRequest';

export const sendRequest = async (request, options = {}) => {
  // Check for running stream and cancel it before sending new request
  if (request.sseStream && typeof request.sseStream.cancel === 'function') {
    try {
      await cancelRequest(request);
    } catch (error) {
      console.warn('Failed to cancel previous SSE stream:', error);
    }
  }
  
  // Continue with normal request sending logic
  // ... existing send logic ...
  
  return result;
};