// Validation utilities for Bruno application

/**
 * Validates that a name is not empty or whitespace-only
 * @param {string} value - The name value to validate
 * @param {string} [fieldName='Name'] - The field name for error messages
 * @returns {string|undefined} Error message or undefined if valid
 */
export const validateNonEmptyName = (value, fieldName = 'Name') => {
  if (!value || typeof value !== 'string') {
    return `${fieldName} is required`;
  }
  
  const trimmedValue = value.trim();
  
  if (trimmedValue === '') {
    return `${fieldName} cannot be whitespace only`;
  }
  
  return undefined;
};

/**
 * Validates that a name meets basic requirements (non-empty, reasonable length)
 * @param {string} value - The name value to validate
 * @param {string} [fieldName='Name'] - The field name for error messages
 * @returns {string|undefined} Error message or undefined if valid
 */
export const validateName = (value, fieldName = 'Name') => {
  const emptyError = validateNonEmptyName(value, fieldName);
  if (emptyError) {
    return emptyError;
  }
  
  // Additional validation: reasonable length limits
  if (value.length > 100) {
    return `${fieldName} is too long (maximum 100 characters)`;
  }
  
  return undefined;
};