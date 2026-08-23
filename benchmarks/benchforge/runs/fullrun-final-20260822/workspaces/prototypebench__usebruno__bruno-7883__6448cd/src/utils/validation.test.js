import { validateNonEmptyName, validateName } from './validation';

// Test cases for whitespace-only validation
describe('validateNonEmptyName', () => {
  test('returns error for null value', () => {
    expect(validateNonEmptyName(null)).toBe('Name is required');
  });

  test('returns error for undefined value', () => {
    expect(validateNonEmptyName(undefined)).toBe('Name is required');
  });

  test('returns error for empty string', () => {
    expect(validateNonEmptyName('')).toBe('Name is required');
  });

  test('returns error for whitespace-only string', () => {
    expect(validateNonEmptyName('   ')).toBe('Name cannot be whitespace only');
    expect(validateNonEmptyName('\t\n\r')).toBe('Name cannot be whitespace only');
  });

  test('returns undefined for valid non-empty string', () => {
    expect(validateNonEmptyName('test')).toBeUndefined();
    expect(validateNonEmptyName('  test  ')).toBeUndefined();
  });
});

describe('validateName', () => {
  test('returns error for whitespace-only string', () => {
    expect(validateName('   ')).toBe('Name cannot be whitespace only');
  });

  test('returns error for very long string', () => {
    const longString = 'a'.repeat(101);
    expect(validateName(longString)).toBe('Name is too long (maximum 100 characters)');
  });

  test('returns undefined for valid name', () => {
    expect(validateName('test')).toBeUndefined();
  });
});