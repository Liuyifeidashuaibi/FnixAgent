const { v4: uuidv4 } = require('uuid');

// Convert Postman collection to Bruno format
module.exports = {
  convert: function(postmanCollection) {
    if (!postmanCollection || !postmanCollection.item) {
      return { requests: [], folders: [] };
    }

    const requests = [];
    const folders = [];

    // Process each item in the collection
    const processItems = (items, parentId = null) => {
      items.forEach(item => {
        if (item.request) {
          // This is a request
          const request = {
            uid: uuidv4(),
            name: item.name || 'Untitled Request',
            method: item.request.method || 'GET',
            url: item.request.url ? this.parseUrl(item.request.url) : '',
            headers: this.parseHeaders(item.request.header),
            body: this.parseBody(item.request.body),
            auth: this.parseAuth(item.request.auth),
            script: {
              req: '',
              res: ''
            },
            tests: '',
            vars: [],
            assertions: [],
            documentation: '',
            type: 'http'
          };

          if (parentId) {
            request.folderUid = parentId;
          }

          requests.push(request);
        } else if (item.item && Array.isArray(item.item)) {
          // This is a folder
          const folder = {
            uid: uuidv4(),
            name: item.name || 'Untitled Folder',
            requests: [],
            folders: []
          };

          if (parentId) {
            folder.parentUid = parentId;
          }

          folders.push(folder);
          
          // Process nested items
          processItems(item.item, folder.uid);
        }
      });
    };

    processItems(postmanCollection.item);

    return { requests, folders };
  },

  // Parse URL from Postman format
  parseUrl: function(urlObj) {
    if (!urlObj) return '';
    
    let urlString = '';
    if (urlObj.raw) {
      urlString = urlObj.raw;
    } else if (urlObj.host && urlObj.path) {
      urlString = urlObj.protocol + '://' + urlObj.host.join('.') + '/' + urlObj.path.join('/');
      if (urlObj.query && urlObj.query.length > 0) {
        urlString += '?' + urlObj.query.map(q => q.key + '=' + (q.value || '')).join('&');
      }
    }
    
    return urlString;
  },

  // Parse headers from Postman format
  parseHeaders: function(headers) {
    if (!headers || !Array.isArray(headers)) return [];
    
    return headers.map(header => ({
      name: header.key,
      value: header.value,
      enabled: header.disabled !== true
    }));
  },

  // Parse body from Postman format
  parseBody: function(body) {
    if (!body) return { mode: 'none', json: '', text: '', xml: '', formUrlEncoded: [], multipartForm: [] };
    
    const result = {
      mode: 'none',
      json: '',
      text: '',
      xml: '',
      formUrlEncoded: [],
      multipartForm: []
    };

    switch (body.mode) {
      case 'raw':
        result.mode = 'text';
        result.text = body.raw || '';
        break;
      case 'urlencoded':
        result.mode = 'formUrlEncoded';
        result.formUrlEncoded = (body.urlencoded || []).map(param => ({
          name: param.key,
          value: param.value,
          enabled: param.disabled !== true
        }));
        break;
      case 'formdata':
        result.mode = 'multipartForm';
        result.multipartForm = (body.formdata || []).map(param => ({
          name: param.key,
          value: param.value,
          type: param.type || 'text',
          enabled: param.disabled !== true
        }));
        break;
      case 'file':
        result.mode = 'file';
        break;
      default:
        if (body.raw) {
          result.mode = 'text';
          result.text = body.raw;
        }
    }
    
    return result;
  },

  // Parse auth from Postman format - FIXED TO HANDLE 'in' FIELD FOR APIKEY
  parseAuth: function(auth) {
    if (!auth || !auth.type) return null;
    
    switch (auth.type) {
      case 'apikey':
        // Handle API Key auth with 'in' field
        const apiKeyAuth = auth.apikey[0];
        const keyName = apiKeyAuth.key || 'key';
        const keyValue = apiKeyAuth.value || '';
        
        // Read the 'in' field - default to 'header' if not specified
        let placement = 'header';
        if (apiKeyAuth.in) {
          if (apiKeyAuth.in === 'query') {
            placement = 'queryparams';
          } else if (apiKeyAuth.in === 'header') {
            placement = 'header';
          }
          // For any other value, default to 'header'
        }
        
        return {
          mode: 'apikey',
          key: keyName,
          value: keyValue,
          placement: placement
        };
        
      case 'bearer':
        const bearerToken = auth.bearer[0]?.token || '';
        return {
          mode: 'bearer',
          token: bearerToken
        };
        
      case 'basic':
        const username = auth.basic[0]?.username || '';
        const password = auth.basic[0]?.password || '';
        return {
          mode: 'basic',
          username: username,
          password: password
        };
        
      case 'none':
      default:
        return null;
    }
  }
};