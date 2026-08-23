/**
 * Workspace validation utilities
 */

/**
 * Validates workspace name format
 * @param {string} name - The workspace name to validate
 * @returns {Object} - Validation result with isValid and error message
 */
export const validateWorkspaceName = (name) => {
  if (!name || typeof name !== 'string') {
    return { isValid: false, error: 'Workspace name is required' };
  }

  const trimmedName = name.trim();
  
  if (!trimmedName) {
    return { isValid: false, error: 'Workspace name cannot be empty' };
  }

  if (trimmedName.length < 2) {
    return { isValid: false, error: 'Workspace name must be at least 2 characters long' };
  }

  if (trimmedName.length > 50) {
    return { isValid: false, error: 'Workspace name cannot exceed 50 characters' };
  }

  // Check for invalid characters
  if (/[^a-zA-Z0-9\-_\s]/.test(trimmedName)) {
    return { 
      isValid: false, 
      error: 'Workspace name can only contain letters, numbers, spaces, hyphens, and underscores' 
    };
  }

  // Check for leading/trailing spaces
  if (name !== trimmedName) {
    return { 
      isValid: false, 
      error: 'Workspace name cannot have leading or trailing spaces' 
    };
  }

  // Check for reserved names
  const reservedNames = ['default', 'temp', 'workspace', 'bruno'];
  if (reservedNames.some(reserved => 
    trimmedName.toLowerCase() === reserved || 
    trimmedName.toLowerCase().startsWith(`${reserved}-`) ||
    trimmedName.toLowerCase().endsWith(`-${reserved}`)
  )) {
    return { 
      isValid: false, 
      error: `"${trimmedName}" is a reserved workspace name` 
    };
  }

  return { isValid: true, error: '' };
};

/**
 * Checks if workspace name already exists
 * @param {string} name - The workspace name to check
 * @param {Array} existingWorkspaces - Array of existing workspace objects
 * @returns {Object} - Validation result with isValid and error message
 */
export const checkDuplicateWorkspaceName = (name, existingWorkspaces = []) => {
  if (!name || !Array.isArray(existingWorkspaces)) {
    return { isValid: true, error: '' };
  }

  const trimmedName = name.trim().toLowerCase();
  
  const exists = existingWorkspaces.some(workspace => 
    workspace.name && workspace.name.toLowerCase() === trimmedName
  );

  if (exists) {
    return { 
      isValid: false, 
      error: `A workspace named "${name}" already exists` 
    };
  }

  return { isValid: true, error: '' };
};

/**
 * Validates custom path for workspace creation
 * @param {string} path - The custom path to validate
 * @returns {Object} - Validation result with isValid and error message
 */
export const validateCustomPath = (path) => {
  if (!path || typeof path !== 'string') {
    return { isValid: true, error: '' };
  }

  const trimmedPath = path.trim();
  
  if (!trimmedPath) {
    return { isValid: true, error: '' };
  }

  // Basic path validation (simplified for frontend)
  if (trimmedPath.length > 255) {
    return { 
      isValid: false, 
      error: 'Path is too long' 
    };
  }

  // Check for dangerous patterns
  if (/\.\.\/\.\.\//.test(trimmedPath) || /\/\.\.\//.test(trimmedPath)) {
    return { 
      isValid: false, 
      error: 'Path contains unsafe directory traversal' 
    };
  }

  return { isValid: true, error: '' };
};

/**
 * Combines all workspace validations
 * @param {string} name - Workspace name
 * @param {string} path - Custom path (optional)
 * @param {Array} existingWorkspaces - Existing workspaces for duplicate checking
 * @returns {Object} - Combined validation result
 */
export const validateWorkspace = (name, path = null, existingWorkspaces = []) => {
  const nameValidation = validateWorkspaceName(name);
  if (!nameValidation.isValid) {
    return nameValidation;
  }

  const duplicateValidation = checkDuplicateWorkspaceName(name, existingWorkspaces);
  if (!duplicateValidation.isValid) {
    return duplicateValidation;
  }

  if (path) {
    const pathValidation = validateCustomPath(path);
    if (!pathValidation.isValid) {
      return pathValidation;
    }
  }

  return { isValid: true, error: '' };
};