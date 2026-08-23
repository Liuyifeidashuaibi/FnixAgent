declare module '../utils/error-formatter' {
  export interface ContextLine {
    lineNumber: number;
    content: string;
    isErrorLine?: boolean;
  }

  export interface ContextResult {
    contextLines: ContextLine[];
    errorLine: {
      lineNumber: number;
      content: string;
    } | null;
    hasContext: boolean;
  }

  export interface FormattedError {
    message: string;
    name: string;
    stack: string;
    fileName: string;
    errorLineNumber: number | null;
    hasContext: boolean;
    context: ContextResult | null;
    isDraft?: boolean;
    scriptType?: string;
    messageWithLocation?: string;
  }

  export function formatErrorWithContext(
    error: Error, 
    options?: {
      scriptContent?: string;
      errorLineNumber?: number;
      fileName?: string;
      contextLines?: number;
    }
  ): FormattedError;

  export function formatDraftScriptError(
    error: Error, 
    draftContent: string, 
    lineNumber: number, 
    scriptType: string
  ): FormattedError;

  export function extractLineNumberFromStack(stack: string): number | null;
}

declare module '../utils/source-context' {
  export interface ContextLine {
    lineNumber: number;
    content: string;
    isErrorLine?: boolean;
  }

  export interface ContextResult {
    contextLines: ContextLine[];
    errorLine: {
      lineNumber: number;
      content: string;
    } | null;
    hasContext: boolean;
  }

  export function getSourceContextFromContent(
    content: string, 
    lineNumber: number, 
    contextLines?: number
  ): ContextResult;

  export function getSourceContextFromContentFormatted(
    content: string, 
    lineNumber: number, 
    options?: {
      contextLines?: number;
      includeLineNumbers?: boolean;
      maxLineLength?: number;
    }
  ): ContextResult & { formatted: true };
}