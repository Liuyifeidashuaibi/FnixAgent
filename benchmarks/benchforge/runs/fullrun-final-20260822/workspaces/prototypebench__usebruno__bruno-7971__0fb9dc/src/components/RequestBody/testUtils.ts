import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

/**
 * Helper to simulate file selection in tests
 */
export const selectFiles = async (fileInput: HTMLElement, files: File[]) => {
  const dataTransfer = new DataTransfer();
  
  files.forEach(file => dataTransfer.items.add(file));
  
  const input = fileInput as HTMLInputElement;
  input.files = dataTransfer.files;
  
  await userEvent.click(input);
};

/**
 * Creates a mock file for testing
 */
export const createMockFile = (name: string, size: number = 1024, type: string = 'text/plain'): File => {
  const content = 'test content';
  const blob = new Blob([content], { type });
  return new File([blob], name, { type, lastModified: Date.now() });
};

/**
 * Gets file chip elements from the DOM
 */
export const getFileChips = () => {
  return screen.getAllByRole('button', { name: /remove/i }).map(btn => btn.parentElement);
};