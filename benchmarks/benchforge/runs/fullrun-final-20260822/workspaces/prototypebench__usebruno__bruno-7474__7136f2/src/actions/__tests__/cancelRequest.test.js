import { cancelRequest } from '../cancelRequest';

describe('cancelRequest', () => {
  it('should return the request object', async () => {
    const request = { id: 'test-request' };

    const result = await cancelRequest(request);

    expect(result).toBe(request);
  });

  it('should cancel SSE stream if it exists', async () => {
    const cancelFn = jest.fn();
    const request = {
      sseStream: {
        cancel: cancelFn
      }
    };

    await cancelRequest(request);

    expect(cancelFn).toHaveBeenCalled();
  });
});