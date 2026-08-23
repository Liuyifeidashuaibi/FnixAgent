declare module '*.css';

declare namespace Multipart {
  interface File {
    id: string;
    name: string;
    path: string;
    size: number;
    type: string;
  }

  interface FormData {
    [key: string]: string | number | boolean | null | undefined;
  }
}

export {};