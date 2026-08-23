import { resolvePacProxy, isValidPacConfig } from '../src/utils/network/pacResolver';

// Mock fetch for testing
global.fetch = jest.fn();

describe('PAC Resolver', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('isValidPacConfig', () => {
    it('should return true for valid URL config', () => {
      const config = {
        pacMode: 'url',
        pacUrl: 'https://example.com/proxy.pac'
      };
      expect(isValidPacConfig(config)).toBe(true);
    });

    it('should return true for valid file config', () => {
      const config = {
        pacMode: 'file',
        pacFile: 'some content',
        pacFileName: 'proxy.pac'
      };
      expect(isValidPacConfig(config)).toBe(true);
    });

    it('should return false for invalid config', () => {
      const config = {
        pacMode: 'url',
        pacUrl: ''
      };
      expect(isValidPacConfig(config)).toBe(false);
    });
  });

  describe('resolvePacProxy', () => {
    it('should resolve proxy from URL', async () => {
      const mockPacContent = `function FindProxyForURL(url, host) {
        if (isInNet(host, "192.168.0.0", "255.255.0.0"))
          return "DIRECT";
        else
          return "PROXY proxy.example.com:8080; DIRECT";
      }`;
      
      fetch.mockResolvedValue({
        ok: true,
        text: () => Promise.resolve(mockPacContent)
      });

      const result = await resolvePacProxy(
        'https://example.com/api',
        { pacMode: 'url', pacUrl: 'https://example.com/proxy.pac' }
      );
      
      expect(result).toEqual({
        type: 'http',
        host: 'proxy.example.com',
        port: 8080
      });
      expect(fetch).toHaveBeenCalledWith('https://example.com/proxy.pac');
    });

    it('should resolve proxy from file content', async () => {
      const mockPacContent = `function FindProxyForURL(url, host) {
        return "PROXY proxy.internal:3128; DIRECT";
      }`;
      
      const result = await resolvePacProxy(
        'https://internal.example.com',
        { 
          pacMode: 'file', 
          pacFile: mockPacContent,
          pacFileName: 'proxy.pac'
        }
      );
      
      expect(result).toEqual({
        type: 'http',
        host: 'proxy.internal',
        port: 3128
      });
    });

    it('should return direct for invalid PAC config', async () => {
      const result = await resolvePacProxy(
        'https://example.com',
        { pacMode: 'url', pacUrl: '' }
      );
      
      expect(result).toEqual({ type: 'direct' });
    });
  });
});