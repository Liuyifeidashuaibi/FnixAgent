import { validateWorkspaceName, checkDuplicateWorkspaceName, validateWorkspace } from '../utils/workspaceValidation';
import { createWorkspace } from '../services/workspaceService';

// Test suite for workspace validation
describe('Workspace Validation', () => {
  test('validates empty name', () => {
    const result = validateWorkspaceName('');
    expect(result.isValid).toBe(false);
    expect(result.error).toBe('Workspace name is required');
  });

  test('validates whitespace-only name', () => {
    const result = validateWorkspaceName('   ');
    expect(result.isValid).toBe(false);
    expect(result.error).toBe('Workspace name cannot be empty');
  });

  test('validates valid name', () => {
    const result = validateWorkspaceName('My Workspace');
    expect(result.isValid).toBe(true);
    expect(result.error).toBe('');
  });

  test('detects duplicate names', () => {
    const existing = [
      { name: 'API Testing' },
      { name: 'Mobile App' }
    ];
    
    const result = checkDuplicateWorkspaceName('API Testing', existing);
    expect(result.isValid).toBe(false);
    expect(result.error).toBe('A workspace named "API Testing" already exists');
  });

  test('combines validations', () => {
    const existing = [{ name: 'Duplicate' }];
    
    // Test invalid name
    let result = validateWorkspace('Invalid@Name', null, existing);
    expect(result.isValid).toBe(false);
    
    // Test duplicate name
    result = validateWorkspace('Duplicate', null, existing);
    expect(result.isValid).toBe(false);
    
    // Test valid case
    result = validateWorkspace('New Workspace', null, existing);
    expect(result.isValid).toBe(true);
  });
});

// Test suite for workspace service
describe('Workspace Service', () => {
  test('creates workspace with default path', async () => {
    const result = await createWorkspace('Test Workspace');
    expect(result).toHaveProperty('id');
    expect(result).toHaveProperty('name', 'Test Workspace');
    expect(result).toHaveProperty('path');
    expect(result.status).toBe('created');
  });

  test('creates workspace with custom path', async () => {
    const result = await createWorkspace('Custom Workspace', '/tmp/test-workspace');
    expect(result).toHaveProperty('id');
    expect(result).toHaveProperty('name', 'Custom Workspace');
    expect(result).toHaveProperty('path', '/tmp/test-workspace');
  });
});