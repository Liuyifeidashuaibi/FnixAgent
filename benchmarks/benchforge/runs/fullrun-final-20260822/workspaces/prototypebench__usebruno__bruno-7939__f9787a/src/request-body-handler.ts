/*
 * Bruno Request Body Handler Extension
 * Extends #7690 to address BRU-3153
 * Handles stream-backed request bodies during variable interpolation
 */

/**
 * Interface for request body handlers
 */
export interface RequestBodyHandler {
  /**
   * Process request body while preserving stream-backed data
   * @param body - The request body
   * @param variables - Variables for interpolation
   * @returns Processed body that maintains byte-exact integrity
   */
  processRequestBody(body: any, variables: Record<string, string>): Promise<any>;
}

/**
 * Stream-aware request body handler that preserves binary data integrity
 */
export class StreamAwareRequestBodyHandler implements RequestBodyHandler {
  
  /**
   * Process request body ensuring stream-backed data is not altered during variable interpolation
   * @param body - The request body (can be string, Buffer, ReadableStream, etc.)
   * @param variables - Variables for interpolation
   * @returns Processed body with preserved byte-exact integrity
   */
  async processRequestBody(body: any, variables: Record<string, string>): Promise<any> {
    // For stream-backed or binary data, skip variable interpolation to preserve exact bytes
    if (this.isStreamBased(body) || this.isBinaryData(body)) {
      return body;
    }
    
    // For text-based bodies, perform variable interpolation as normal
    return this.interpolateVariables(body, variables);
  }
  
  /**
   * Check if body is stream-based (ReadableStream, Buffer, etc.)
   */
  private isStreamBased(body: any): boolean {
    return body && (
      typeof body.pipe === 'function' ||
      body instanceof Buffer ||
      (typeof body === 'object' && body.constructor && 
       body.constructor.name === 'ReadableStream') ||
      (typeof body === 'object' && body.readable)
    );
  }
  
  /**
   * Check if body contains binary data
   */
  private isBinaryData(body: any): boolean {
    if (body instanceof Buffer) {
      return true;
    }
    
    if (typeof body === 'string') {
      // Check for binary content in string (non-printable characters)
      const binaryRegex = /[^\x20-\x7E\t\n\r]/;
      return binaryRegex.test(body);
    }
    
    return false;
  }
  
  /**
   * Perform variable interpolation on text-based bodies
   */
  private interpolateVariables(body: string, variables: Record<string, string>): string {
    let result = body;
    
    Object.entries(variables).forEach(([key, value]) => {
      const regex = new RegExp(`\{\{\s*${key}\s*\}\}`, 'g');
      result = result.replace(regex, value);
    });
    
    return result;
  }
}

// Export default instance
export const requestBodyHandler = new StreamAwareRequestBodyHandler();