export const generateGraphQLQuery = (nodes: any[]): string => {
  if (nodes.length === 0) return 'query {}';
  
  const queryParts = nodes.map(node => {
    let args = '';
    if (node.args && node.args.length > 0) {
      const argStrings = node.args
        .filter((arg: any) => arg.value !== undefined && arg.value !== null && arg.value !== '')
        .map((arg: any) => `${arg.name}: ${JSON.stringify(arg.value)}`);
      if (argStrings.length > 0) {
        args = `(${argStrings.join(', ')})`;
      }
    }
    
    let fields = '';
    if (node.fields && node.fields.length > 0) {
      fields = ` {
        ${node.fields.map((f: any) => f.name).join('\n        ')}
      }`;
    }
    
    return `${node.name}${args}${fields}`;
  });
  
  return `query {
    ${queryParts.join('\n    ')}
  }`;
};

export const parseGraphQLQuery = (query: string): any[] => {
  // Simple parser for demo purposes
  // In a real implementation, this would use a proper GraphQL parser
  const nodes: any[] = [];
  
  // Extract root query fields
  const queryMatch = query.match(/query\s*\{([^}]+)\}/s);
  if (queryMatch && queryMatch[1]) {
    const fields = queryMatch[1].trim().split(/\n\s*/).filter(f => f.trim());
    
    fields.forEach(field => {
      const fieldMatch = field.match(/^(\w+)(?:\(([^)]+)\))?(?:\s*\{([^}]+)\})?/);
      if (fieldMatch) {
        const name = fieldMatch[1];
        const args = fieldMatch[2] ? 
          fieldMatch[2].split(',').map(a => {
            const [argName, argValue] = a.split(':').map(s => s.trim());
            return { name: argName, value: argValue ? argValue.replace(/['"\s]/g, '') : '' };
          }) : [];
        
        nodes.push({
          name,
          args,
          fields: []
        });
      }
    });
  }
  
  return nodes;
};

export const validateGraphQLVariables = (variables: Record<string, any>, schema: any): string[] => {
  const errors: string[] = [];
  
  // Simple validation - in real implementation would check against schema types
  Object.entries(variables).forEach(([key, value]) => {
    if (value === null || value === undefined) {
      errors.push(`Variable '${key}' cannot be null or undefined`);
    }
  });
  
  return errors;
};