import React, { useRef } from 'react';
import { usePersistedEditorScroll, usePersistedContainerScroll } from '../hooks';

// Example: Request Body Editor Component
const RequestBodyEditor = ({ tabUid, requestUid }: { tabUid: string; requestUid: string }) => {
  const { editorRef, isRestored } = usePersistedEditorScroll(tabUid, requestUid);

  return (
    <div 
      ref={editorRef} 
      className="request-body-editor"
      style={{ height: '400px', overflow: 'auto' }}
    >
      {/* Editor content would go here */}
      <pre>
        {`{
  "name": "John Doe",
  "email": "john@example.com",
  "address": {
    "street": "123 Main St",
    "city": "Anytown",
    "state": "CA",
    "zip": "12345"
  },
  "preferences": {
    "notifications": true,
    "newsletter": false,
    "marketing": true
  }
}`}
      </pre>
      {!isRestored && <div>Loading scroll position...</div>}
    </div>
  );
};

// Example: Response Pane Component
const ResponsePane = ({ tabUid, responseUid }: { tabUid: string; responseUid: string }) => {
  const { containerRef, isRestored } = usePersistedContainerScroll(tabUid, responseUid);

  return (
    <div 
      ref={containerRef} 
      className="response-pane"
      style={{ height: '500px', overflow: 'auto' }}
    >
      {/* Response content would go here */}
      <pre>
        {`HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 1234
Date: Mon, 22 Aug 2026 10:30:45 GMT

{
  "status": "success",
  "data": {
    "id": 12345,
    "name": "Sample Data",
    "description": "This is a sample response with lots of content that requires scrolling...",
    "items": [
      {"id": 1, "name": "Item 1", "value": "value1"},
      {"id": 2, "name": "Item 2", "value": "value2"},
      {"id": 3, "name": "Item 3", "value": "value3"},
      {"id": 4, "name": "Item 4", "value": "value4"},
      {"id": 5, "name": "Item 5", "value": "value5"},
      {"id": 6, "name": "Item 6", "value": "value6"},
      {"id": 7, "name": "Item 7", "value": "value7"},
      {"id": 8, "name": "Item 8", "value": "value8"},
      {"id": 9, "name": "Item 9", "value": "value9"},
      {"id": 10, "name": "Item 10", "value": "value10"}
    ]
  }
}`}
      </pre>
      {!isRestored && <div>Loading scroll position...</div>}
    </div>
  );
};

// Example: Folder Settings Component
const FolderSettings = ({ tabUid, folderUid }: { tabUid: string; folderUid: string }) => {
  const { containerRef, isRestored } = usePersistedContainerScroll(tabUid, folderUid);

  return (
    <div 
      ref={containerRef} 
      className="folder-settings"
      style={{ height: '400px', overflow: 'auto' }}
    >
      {/* Folder settings content would go here */}
      <h3>Folder Settings</h3>
      <div>
        <label>Folder Name: <input type="text" defaultValue="My Folder" /></label>
      </div>
      <div>
        <label>Description: <textarea rows={5} cols={50}>This is a description of the folder...</textarea></label>
      </div>
      <div>
        <h4>Environment Variables</h4>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Value</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {[...Array(20)].map((_, i) => (
              <tr key={i}>
                <td><input type="text" defaultValue={`VAR_${i}`} /></td>
                <td><input type="text" defaultValue={`value_${i}`} /></td>
                <td><button>Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!isRestored && <div>Loading scroll position...</div>}
    </div>
  );
};

export { RequestBodyEditor, ResponsePane, FolderSettings };