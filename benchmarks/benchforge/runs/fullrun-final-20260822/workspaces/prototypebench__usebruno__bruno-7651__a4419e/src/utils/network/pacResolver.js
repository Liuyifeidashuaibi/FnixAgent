import { parse as parseUrl } from 'url';

// Simple PAC resolver implementation
// In a real implementation, this would use a proper PAC parser
// like pac-resolver or similar library

const DEFAULT_PROXY = 'DIRECT';

// Basic PAC function evaluation
const evaluatePacScript = (pacScript, url, host) => {
  try {
    // Create a sandboxed environment for PAC script execution
    // This is a simplified version - real implementation would be more robust
    
    // Extract the FindProxyForURL function from the PAC script
    const findProxyRegex = /function\s+FindProxyForURL\s*\(\s*[^)]+\s*\)\s*\{([^}]+)\}/i;
    const match = pacScript.match(findProxyRegex);
    
    if (!match) {
      return DEFAULT_PROXY;
    }
    
    // Simple evaluation of common PAC functions
    // In production, use a proper PAC parser library
    const pacFunctions = {
      'isInNet': (host, pattern, mask) => {
        // Simplified IP matching logic
        return host === pattern || host.includes(pattern);
      },
      'dnsDomainIs': (host, domain) => {
        return host.endsWith(domain) || host === domain;
      },
      'localHostOrDomainIs': (host, hostdom) => {
        return host === hostdom || host.endsWith('.' + hostdom);
      },
      'isPlainHostName': (host) => {
        return !host.includes('.');
      },
      'shExpMatch': (str, pattern) => {
        // Simple shell expression matching
        const regex = new RegExp('^' + pattern.replace(/\./g, '\\.').replace(/\*/g, '.*') + '$');
        return regex.test(str);
      }
    };
    
    // For demo purposes, return DIRECT for now
    // Real implementation would parse and execute the PAC script
    return DEFAULT_PROXY;
    
  } catch (error) {
    console.warn('Error evaluating PAC script:', error);
    return DEFAULT_PROXY;
  }
};

// Resolve proxy for given URL using PAC script
export const resolvePacProxy = async (url, pacConfig) => {
  try {
    let pacScript = '';
    
    if (pacConfig.pacMode === 'url' && pacConfig.pacUrl) {
      // Fetch PAC script from URL
      const response = await fetch(pacConfig.pacUrl);
      if (!response.ok) {
        throw new Error(`Failed to fetch PAC script: ${response.status} ${response.statusText}`);
      }
      pacScript = await response.text();
    } else if (pacConfig.pacMode === 'file' && pacConfig.pacFile) {
      // Use uploaded PAC file content
      pacScript = pacConfig.pacFile;
    }
    
    if (!pacScript) {
      return null;
    }
    
    const parsedUrl = parseUrl(url);
    const host = parsedUrl.hostname || '';
    
    // Evaluate PAC script to get proxy configuration
    const proxyResult = evaluatePacScript(pacScript, url, host);
    
    // Parse proxy result (e.g., "PROXY proxy.example.com:8080; DIRECT")
    if (proxyResult.includes('PROXY')) {
      const proxyMatch = proxyResult.match(/PROXY\s+([^;]+)/i);
      if (proxyMatch && proxyMatch[1]) {
        const [host, port] = proxyMatch[1].split(':');
        return {
          type: 'http',
          host: host.trim(),
          port: parseInt(port) || 8080
        };
      }
    }
    
    // Default to DIRECT
    return {
      type: 'direct'
    };
    
  } catch (error) {
    console.error('Error resolving PAC proxy:', error);
    return {
      type: 'direct'
    };
  }
};

// Helper to check if PAC configuration is valid
export const isValidPacConfig = (pacConfig) => {
  if (!pacConfig) return false;
  
  if (pacConfig.pacMode === 'url') {
    return pacConfig.pacUrl && pacConfig.pacUrl.trim() !== '';
  }
  
  if (pacConfig.pacMode === 'file') {
    return pacConfig.pacFile !== null && pacConfig.pacFileName && pacConfig.pacFileName.endsWith('.pac');
  }
  
  return false;
};