import React, { useState, useEffect } from 'react';
import HeadersPane from './HeadersPane';
import AssertionsPane from './AssertionsPane';
import BodyPane from './BodyPane';

/**
 * RequestEditor - Main request editor component with tab navigation
 * and scroll position persistence across panes
 */
const RequestEditor = () => {
  const [activeTab, setActiveTab] = useState('headers');
  const [headers, setHeaders] = useState([
    { key: 'Content-Type', value: 'application/json' },
    { key: 'Authorization', value: 'Bearer token123' }
  ]);
  const [assertions, setAssertions] = useState([
    { expression: 'response.status == 200', type: 'response-status' },
    { expression: 'response.body.id != null', type: 'response-body' }
  ]);
  const [body, setBody] = useState('{\n  "name": "John",\n  "age": 30\n}');

  // Restore scroll position when tab changes
  useEffect(() => {
    // This would trigger the useScrollPosition hook to restore position
    // for the newly active tab
  }, [activeTab]);

  return (
    <div className="bruno-request-editor" style={{ maxWidth: '800px', margin: '0 auto' }}>
      <div className="tabs" style={{ display: 'flex', borderBottom: '1px solid #ddd' }}>
        <button 
          onClick={() => setActiveTab('headers')}
          style={{
            padding: '10px 20px',
            border: 'none',
            background: activeTab === 'headers' ? '#007bff' : 'transparent',
            color: activeTab === 'headers' ? 'white' : '#333',
            cursor: 'pointer'
          }}
        >
          Headers
        </button>
        <button 
          onClick={() => setActiveTab('assertions')}
          style={{
            padding: '10px 20px',
            border: 'none',
            background: activeTab === 'assertions' ? '#007bff' : 'transparent',
            color: activeTab === 'assertions' ? 'white' : '#333',
            cursor: 'pointer'
          }}
        >
          Assertions
        </button>
        <button 
          onClick={() => setActiveTab('body')}
          style={{
            padding: '10px 20px',
            border: 'none',
            background: activeTab === 'body' ? '#007bff' : 'transparent',
            color: activeTab === 'body' ? 'white' : '#333',
            cursor: 'pointer'
          }}
        >
          Body
        </button>
      </div>
      
      <div className="pane-content" style={{ padding: '20px' }}>
        {activeTab === 'headers' && (
          <HeadersPane 
            headers={headers} 
            onHeadersChange={setHeaders} 
          />
        )}
        {activeTab === 'assertions' && (
          <AssertionsPane 
            assertions={assertions} 
            onAssertionsChange={setAssertions} 
          />
        )}
        {activeTab === 'body' && (
          <BodyPane 
            body={body} 
            onBodyChange={setBody} 
          />
        )}
      </div>
    </div>
  );
};

export default RequestEditor;
