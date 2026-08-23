import React from 'react';
import { usePersistedEditorScroll, usePersistedContainerScroll } from '../hooks';

/**
 * Example Bruno Request Tab Component
 * This shows how the hooks would be integrated into Bruno's actual UI components
 */
const BrunoRequestTab = ({ 
  tabUid, 
  request, 
  response,
  folder 
}: { 
  tabUid: string; 
  request: any; 
  response: any;
  folder: any;
}) => {
  // Persist scroll for request headers editor
  const { editorRef: headersRef, isRestored: headersRestored } = 
    usePersistedEditorScroll(tabUid, `${request.id}-headers`);

  // Persist scroll for request body editor
  const { editorRef: bodyRef, isRestored: bodyRestored } = 
    usePersistedEditorScroll(tabUid, `${request.id}-body`);

  // Persist scroll for request script editor
  const { editorRef: scriptRef, isRestored: scriptRestored } = 
    usePersistedEditorScroll(tabUid, `${request.id}-script`);

  // Persist scroll for response pane
  const { containerRef: responseRef, isRestored: responseRestored } = 
    usePersistedContainerScroll(tabUid, `${response.id}-response`);

  // Persist scroll for folder settings
  const { containerRef: folderRef, isRestored: folderRestored } = 
    usePersistedContainerScroll(tabUid, `${folder.id}-settings`);

  return (
    <div className="bruno-request-tab">
      <div className="tab-header">
        <h2>{request.name}</h2>
      </div>
      
      <div className="tab-content">
        {/* Headers Editor */}
        <div className="headers-section">
          <h3>Headers</h3>
          <div ref={headersRef} className="editor-container" style={{ height: '200px', overflow: 'auto' }}>
            {/* Headers content */}
            <pre>{JSON.stringify(request.headers, null, 2)}</pre>
          </div>
          {!headersRestored && <div className="loading">Loading headers scroll position...</div>}
        </div>
        
        {/* Body Editor */}
        <div className="body-section">
          <h3>Body</h3>
          <div ref={bodyRef} className="editor-container" style={{ height: '300px', overflow: 'auto' }}>
            {/* Body content */}
            <pre>{JSON.stringify(request.body, null, 2)}</pre>
          </div>
          {!bodyRestored && <div className="loading">Loading body scroll position...</div>}
        </div>
        
        {/* Script Editor */}
        <div className="script-section">
          <h3>Script</h3>
          <div ref={scriptRef} className="editor-container" style={{ height: '250px', overflow: 'auto' }}>
            {/* Script content */}
            <pre>{request.script || '// Pre-request script'}</pre>
          </div>
          {!scriptRestored && <div className="loading">Loading script scroll position...</div>}
        </div>
        
        {/* Response Pane */}
        <div className="response-section">
          <h3>Response</h3>
          <div ref={responseRef} className="response-container" style={{ height: '400px', overflow: 'auto' }}>
            {/* Response content */}
            <pre>{JSON.stringify(response.data, null, 2)}</pre>
          </div>
          {!responseRestored && <div className="loading">Loading response scroll position...</div>}
        </div>
        
        {/* Folder Settings */}
        <div className="folder-settings-section">
          <h3>Folder Settings</h3>
          <div ref={folderRef} className="folder-settings-container" style={{ height: '350px', overflow: 'auto' }}>
            {/* Folder settings content */}
            <div>
              <label>Folder Name: <input type="text" defaultValue={folder.name} /></label>
            </div>
            <div>
              <label>Description: <textarea rows={3} cols={50}>{folder.description}</textarea></label>
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
                  {folder.envVars.map((envVar: any, index: number) => (
                    <tr key={index}>
                      <td><input type="text" defaultValue={envVar.name} /></td>
                      <td><input type="text" defaultValue={envVar.value} /></td>
                      <td><button>Remove</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {!folderRestored && <div className="loading">Loading folder settings scroll position...</div>}
        </div>
      </div>
    </div>
  );
};

export default BrunoRequestTab;