/*
 * HeaderList implementation for Bruno
 * Follows MDN Headers API with Bruno-specific extensions
 */

class HeaderList {
  constructor(headersObj, options = {}) {
    this._headers = headersObj;
    this._isReadOnly = options.readOnly || false;
    this._dynamic = options.dynamic !== false;
    this._caseInsensitive = options.caseInsensitive !== false;
  }

  // Helper methods
  _normalizeKey(key) {
    if (typeof key === 'string') {
      return this._caseInsensitive ? key.toLowerCase() : key;
    }
    return key;
  }

  _findHeader(key, value) {
    const normalizedKey = this._normalizeKey(key);
    
    for (let i = 0; i < this._headers.length; i++) {
      const header = this._headers[i];
      const headerKey = this._caseInsensitive ? header.key.toLowerCase() : header.key;
      
      if (headerKey === normalizedKey) {
        if (value === undefined) {
          return header;
        } else if (header.value === value) {
          return header;
        }
      }
    }
    return undefined;
  }

  _getHeadersArray() {
    // For dynamic mode, read from live req.headers object
    if (this._dynamic && typeof this._headers === 'object' && this._headers !== null) {
      // Convert the raw headers object to array format
      const headersArray = [];
      for (const [key, value] of Object.entries(this._headers)) {
        if (Array.isArray(value)) {
          // Handle multiple values (though Bruno doesn't support duplicates)
          for (const v of value) {
            headersArray.push({ key, value: v.toString() });
          }
        } else {
          headersArray.push({ key, value: value.toString() });
        }
      }
      return headersArray;
    }
    return this._headers;
  }

  // Read Methods
  get(name) {
    const header = this._findHeader(name);
    return header ? header.value : undefined;
  }

  one(name) {
    const header = this._findHeader(name);
    return header ? { key: header.key, value: header.value } : undefined;
  }

  all() {
    const headersArray = this._getHeadersArray();
    // Return cloned array
    return headersArray.map(h => ({ ...h }));
  }

  count() {
    return this._getHeadersArray().length;
  }

  // Search Methods
  has(name, value) {
    if (typeof name === 'object' && name !== null && 'key' in name) {
      return this._findHeader(name.key) !== undefined;
    }
    
    if (value !== undefined) {
      return this._findHeader(name, value) !== undefined;
    }
    
    return this._findHeader(name) !== undefined;
  }

  find(fn, context) {
    const headersArray = this._getHeadersArray();
    for (let i = 0; i < headersArray.length; i++) {
      if (fn.call(context, headersArray[i], i)) {
        return { ...headersArray[i] };
      }
    }
    return undefined;
  }

  filter(fn, context) {
    const headersArray = this._getHeadersArray();
    return headersArray.filter((h, i) => fn.call(context, h, i)).map(h => ({ ...h }));
  }

  indexOf(item) {
    const headersArray = this._getHeadersArray();
    if (typeof item === 'string') {
      const normalizedItem = this._normalizeKey(item);
      for (let i = 0; i < headersArray.length; i++) {
        const headerKey = this._caseInsensitive ? headersArray[i].key.toLowerCase() : headersArray[i].key;
        if (headerKey === normalizedItem) {
          return i;
        }
      }
    } else if (typeof item === 'object' && item !== null && 'key' in item) {
      const normalizedKey = this._normalizeKey(item.key);
      for (let i = 0; i < headersArray.length; i++) {
        const headerKey = this._caseInsensitive ? headersArray[i].key.toLowerCase() : headersArray[i].key;
        if (headerKey === normalizedKey) {
          return i;
        }
      }
    }
    return -1;
  }

  // Iteration Methods
  forEach(fn, context) {
    const headersArray = this._getHeadersArray();
    for (let i = 0; i < headersArray.length; i++) {
      fn.call(context, { ...headersArray[i] }, i);
    }
  }

  map(fn, context) {
    const headersArray = this._getHeadersArray();
    return headersArray.map((h, i) => fn.call(context, { ...h }, i));
  }

  reduce(fn, initial, context) {
    const headersArray = this._getHeadersArray();
    let accumulator = initial;
    for (let i = 0; i < headersArray.length; i++) {
      accumulator = fn.call(context, accumulator, { ...headersArray[i] }, i);
    }
    return accumulator;
  }

  // Transform Methods
  toObject(excludeDisabled = true, caseSensitive = false, multiValue = false, sanitizeKeys = true) {
    const result = {};
    const headersArray = this._getHeadersArray();
    
    for (const header of headersArray) {
      if (excludeDisabled && header.disabled) continue;
      
      let key = caseSensitive ? header.key : header.key.toLowerCase();
      if (sanitizeKeys) {
        key = key.replace(/[^a-zA-Z0-9-_]/g, '-');
      }
      
      if (multiValue && result[key]) {
        if (!Array.isArray(result[key])) {
          result[key] = [result[key]];
        }
        result[key].push(header.value);
      } else {
        result[key] = header.value;
      }
    }
    
    return result;
  }

  toString() {
    const headersArray = this._getHeadersArray();
    const lines = [];
    
    for (const header of headersArray) {
      if (!header.disabled) {
        lines.push(`${header.key}: ${header.value}`);
      }
    }
    
    return lines.join('\n');
  }

  toJSON() {
    return this.all();
  }

  // Write Methods (only for writable HeaderList)
  append(headerObj, value) {
    if (this._isReadOnly) {
      throw new Error('HeaderList is read-only');
    }
    
    // Delegate to set() as per spec
    return this.set(headerObj, value);
  }

  set(headerObj, value) {
    if (this._isReadOnly) {
      throw new Error('HeaderList is read-only');
    }
    
    let key, val;
    
    if (typeof headerObj === 'string' && value === undefined) {
      // String format: "Key: Value"
      const parts = headerObj.split(':');
      if (parts.length >= 2) {
        key = parts[0].trim();
        val = parts.slice(1).join(':').trim();
      }
    } else if (typeof headerObj === 'string' && value !== undefined) {
      // Two-arg form: set('Key', 'Value')
      key = headerObj;
      val = value;
    } else if (typeof headerObj === 'object' && headerObj !== null && 'key' in headerObj && 'value' in headerObj) {
      // Object format: { key: 'Key', value: 'Value' }
      key = headerObj.key;
      val = headerObj.value;
    } else {
      return null;
    }
    
    if (!key || val === undefined) {
      return null;
    }
    
    // Find existing header
    const existingIndex = this.indexOf(key);
    
    if (existingIndex === -1) {
      // Add new header
      if (Array.isArray(this._headers)) {
        this._headers.push({ key, value: val.toString() });
      } else if (typeof this._headers === 'object') {
        // Update raw headers object
        this._headers[key] = val.toString();
      }
      return true;
    } else {
      // Update existing header
      if (Array.isArray(this._headers)) {
        this._headers[existingIndex] = { key, value: val.toString() };
      } else if (typeof this._headers === 'object') {
        this._headers[key] = val.toString();
      }
      return false;
    }
  }

  delete(predicate, context) {
    if (this._isReadOnly) {
      throw new Error('HeaderList is read-only');
    }
    
    if (typeof predicate === 'string') {
      // Delete by key
      const index = this.indexOf(predicate);
      if (index !== -1) {
        if (Array.isArray(this._headers)) {
          this._headers.splice(index, 1);
        } else if (typeof this._headers === 'object') {
          delete this._headers[predicate];
        }
      }
    } else if (typeof predicate === 'function') {
      // Delete by predicate
      if (Array.isArray(this._headers)) {
        for (let i = this._headers.length - 1; i >= 0; i--) {
          if (predicate.call(context, this._headers[i], i)) {
            this._headers.splice(i, 1);
          }
        }
      } else if (typeof this._headers === 'object') {
        // For object mode, we'd need to iterate and delete
        const keysToDelete = [];
        for (const key in this._headers) {
          const header = { key, value: this._headers[key] };
          if (predicate.call(context, header, 0)) {
            keysToDelete.push(key);
          }
        }
        for (const key of keysToDelete) {
          delete this._headers[key];
        }
      }
    } else if (typeof predicate === 'object' && predicate !== null && 'key' in predicate) {
      // Delete by object
      const index = this.indexOf(predicate);
      if (index !== -1) {
        if (Array.isArray(this._headers)) {
          this._headers.splice(index, 1);
        } else if (typeof this._headers === 'object') {
          delete this._headers[predicate.key];
        }
      }
    }
  }

  clear() {
    if (this._isReadOnly) {
      throw new Error('HeaderList is read-only');
    }
    
    if (Array.isArray(this._headers)) {
      this._headers.length = 0;
    } else if (typeof this._headers === 'object') {
      for (const key in this._headers) {
        delete this._headers[key];
      }
    }
  }

  populate(items) {
    if (this._isReadOnly) {
      throw new Error('HeaderList is read-only');
    }
    
    if (typeof items === 'string') {
      // Parse multi-line string
      const lines = items.split('\n').filter(line => line.trim() !== '');
      const headersToPopulate = [];
      
      for (const line of lines) {
        const parts = line.split(':');
        if (parts.length >= 2) {
          const key = parts[0].trim();
          const value = parts.slice(1).join(':').trim();
          headersToPopulate.push({ key, value });
        }
      }
      
      items = headersToPopulate;
    }
    
    if (Array.isArray(items)) {
      for (const item of items) {
        if (typeof item === 'object' && item !== null && 'key' in item && 'value' in item) {
          // Skip if key already exists (case-insensitive)
          const existingIndex = this.indexOf(item.key);
          if (existingIndex === -1) {
            this.append(item);
          }
        }
      }
    }
  }

  repopulate(items) {
    if (this._isReadOnly) {
      throw new Error('HeaderList is read-only');
    }
    
    this.clear();
    this.populate(items);
  }

  assimilate(source, prune = false) {
    if (this._isReadOnly) {
      throw new Error('HeaderList is read-only');
    }
    
    // Get headers from source
    let sourceHeaders = [];
    
    if (source instanceof HeaderList) {
      sourceHeaders = source.all();
    } else if (Array.isArray(source)) {
      sourceHeaders = source;
    } else if (typeof source === 'object' && source !== null) {
      // Convert object to array
      for (const [key, value] of Object.entries(source)) {
        if (Array.isArray(value)) {
          for (const v of value) {
            sourceHeaders.push({ key, value: v.toString() });
          }
        } else {
          sourceHeaders.push({ key, value: value.toString() });
        }
      }
    }
    
    if (prune) {
      // Remove headers not present in source
      const sourceKeys = new Set();
      for (const header of sourceHeaders) {
        sourceKeys.add(this._normalizeKey(header.key));
      }
      
      // Remove headers not in sourceKeys
      if (Array.isArray(this._headers)) {
        for (let i = this._headers.length - 1; i >= 0; i--) {
          const headerKey = this._caseInsensitive ? this._headers[i].key.toLowerCase() : this._headers[i].key;
          if (!sourceKeys.has(headerKey)) {
            this._headers.splice(i, 1);
          }
        }
      } else if (typeof this._headers === 'object') {
        for (const key in this._headers) {
          const headerKey = this._caseInsensitive ? key.toLowerCase() : key;
          if (!sourceKeys.has(headerKey)) {
            delete this._headers[key];
          }
        }
      }
    }
    
    // Populate with source headers
    this.populate(sourceHeaders);
  }
}

// Export for use in Bruno's script environment
if (typeof module !== 'undefined' && module.exports) {
  module.exports = HeaderList;
}
