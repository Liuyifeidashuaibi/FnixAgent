/*
 * Integration code for adding headerList property to req and res objects
 * in Bruno's script execution environment
 */

// Import HeaderList class
const HeaderList = require('./../headers/HeaderList');

/**
 * Enhances the req object with headerList property
 * @param {Object} req - The request object
 * @returns {Object} Enhanced req object
 */
function enhanceReqWithHeaderList(req) {
  // Create writable HeaderList for req
  // Uses dynamic mode to read from live req.headers
  const reqHeaderList = new HeaderList(req.headers, {
    dynamic: true,
    caseInsensitive: true
  });
  
  // Add headerList property to req
  Object.defineProperty(req, 'headerList', {
    get() {
      return reqHeaderList;
    },
    enumerable: true,
    configurable: true
  });
  
  return req;
}

/**
 * Enhances the res object with headerList property
 * @param {Object} res - The response object
 * @returns {Object} Enhanced res object
 */
function enhanceResWithHeaderList(res) {
  // Create read-only HeaderList for res
  // Uses static mode since response headers are typically set once
  const resHeaderList = new HeaderList(res.headers, {
    readOnly: true,
    caseInsensitive: true
  });
  
  // Add headerList property to res
  Object.defineProperty(res, 'headerList', {
    get() {
      return resHeaderList;
    },
    enumerable: true,
    configurable: true
  });
  
  return res;
}

/**
 * Factory function to create enhanced req and res objects
 * @param {Object} req - Original request object
 * @param {Object} res - Original response object
 * @returns {Object} Object containing enhanced req and res
 */
function createEnhancedScriptObjects(req, res) {
  return {
    req: enhanceReqWithHeaderList(req),
    res: enhanceResWithHeaderList(res)
  };
}

// Export functions
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    enhanceReqWithHeaderList,
    enhanceResWithHeaderList,
    createEnhancedScriptObjects
  };
}
