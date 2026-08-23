export const cancelRequest = async (request) => {
  if (request.sseStream && typeof request.sseStream.cancel === 'function') {
    await request.sseStream.cancel();
  }
  
  // Add return to make it properly chainable
  return request;
};