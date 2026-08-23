import { sendRequest } from '../sendRequest';
import { cancelRequest } from '../cancelRequest';

// Mock cancelRequest
jest.mock('../cancelRequest', () => ({
  cancelRequest: jest.fn()
}));

describe('sendRequest', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should cancel previous SSE stream before sending new request', async () => {
    const request = {
      sseStream: {
        cancel: jest.fn()
      }
    };

    await sendRequest(request);

    expect(cancelRequest).toHaveBeenCalledWith(request);
  });

  it('should not throw error if no SSE stream exists', async () => {
    const request = {};

    await expect(sendRequest(request)).resolves.not.toThrow();
  });
});