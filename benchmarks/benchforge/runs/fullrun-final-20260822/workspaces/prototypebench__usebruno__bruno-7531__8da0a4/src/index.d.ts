declare module '../utils/multipart-boundary' {
  export function getBoundaryFromContentType(contentType: string): string | null;
  export function generateRandomBoundary(): string;
  export function getMultipartBoundary(contentType: string, preserveUserBoundary?: boolean): string;
}

declare module '../requests/http-client' {
  export function processMultipartRequestBody(request: any): any;
  export function createMultipartBody(request: any, boundary: string): string;
}