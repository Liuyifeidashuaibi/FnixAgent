import React, { useState, useEffect } from 'react';

interface RunnerTabProps {
  // Props for the runner tab
}

const RunnerTab: React.FC<RunnerTabProps> = ({}) => {
  const [isRunning, setIsRunning] = useState(false);
  const [runResults, setRunResults] = useState<any[]>([]);
  
  // Theme-based styling classes
  const themeClasses = {
    container: 'bg-surface text-text-primary',
    section: 'bg-surface-secondary border border-border rounded-lg p-4 mb-4',
    heading: 'text-lg font-semibold mb-3',
    inputGroup: 'mb-3',
    label: 'block text-sm font-medium mb-1',
    input: 'w-full px-3 py-2 bg-surface-tertiary border border-border rounded focus:outline-none focus:ring-2 focus:ring-brand',
    button: 'px-4 py-2 bg-brand text-white rounded hover:bg-brand-dark transition-colors',
    runButton: 'px-6 py-3 bg-brand text-white rounded-lg font-medium hover:bg-brand-dark transition-colors',
    statusBadge: 'inline-flex items-center px-2 py-1 rounded text-xs font-medium',
  };

  const handleRunCollection = () => {
    setIsRunning(true);
    // Simulate API call or collection running
    setTimeout(() => {
      setRunResults([
        { id: 1, name: 'GET /api/users', status: 'success', time: '124ms', responseCode: 200 },
        { id: 2, name: 'POST /api/users', status: 'error', time: '89ms', responseCode: 500 },
        { id: 3, name: 'PUT /api/users/1', status: 'success', time: '67ms', responseCode: 200 }
      ]);
      setIsRunning(false);
    }, 2000);
  };

  return (
    <div className={themeClasses.container}>
      <div className="max-w-6xl mx-auto p-4">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold">Collection Runner</h1>
          <p className="text-text-secondary mt-1">Run your entire collection or selected requests</p>
        </div>

        {/* Two Separate Sections */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Configuration Section */}
          <div className={themeClasses.section}>
            <h2 className={themeClasses.heading}>Configuration</h2>
            
            <div className={themeClasses.inputGroup}>
              <label className={themeClasses.label}>Delay between requests (ms)</label>
              <input 
                type="number" 
                defaultValue="0" 
                className={themeClasses.input}
                placeholder="Enter delay in milliseconds"
              />
            </div>
            
            <div className={themeClasses.inputGroup}>
              <label className={themeClasses.label}>Include tags</label>
              <input 
                type="text" 
                className={themeClasses.input}
                placeholder="Comma-separated tags"
              />
            </div>
            
            <div className={themeClasses.inputGroup}>
              <label className={themeClasses.label}>Exclude tags</label>
              <input 
                type="text" 
                className={themeClasses.input}
                placeholder="Comma-separated tags"
              />
            </div>
            
            <div className={themeClasses.inputGroup}>
              <label className={themeClasses.label}>Environment</label>
              <select className={themeClasses.input}>
                <option>Default</option>
                <option>Development</option>
                <option>Production</option>
              </select>
            </div>
          </div>

          {/* Run Controls Section */}
          <div className={themeClasses.section}>
            <h2 className={themeClasses.heading}>Run Collection</h2>
            
            <div className="space-y-4">
              <div>
                <h3 className="font-medium mb-2">Select Requests</h3>
                <div className="flex flex-wrap gap-2">
                  <button className={`${themeClasses.button} text-sm`}>All Requests</button>
                  <button className={`${themeClasses.button} text-sm bg-brand-light text-brand`}>Selected Only</button>
                  <button className={`${themeClasses.button} text-sm`}>By Tag</button>
                </div>
              </div>
              
              <div>
                <h3 className="font-medium mb-2">Run Options</h3>
                <div className="flex items-center space-x-3">
                  <input type="checkbox" id="stopOnError" className="rounded" />
                  <label htmlFor="stopOnError" className="text-sm">Stop on first error</label>
                </div>
                <div className="flex items-center space-x-3 mt-2">
                  <input type="checkbox" id="clearConsole" className="rounded" />
                  <label htmlFor="clearConsole" className="text-sm">Clear console before run</label>
                </div>
              </div>
              
              <div className="pt-4">
                <button 
                  onClick={handleRunCollection}
                  disabled={isRunning}
                  className={`${themeClasses.runButton} w-full ${isRunning ? 'opacity-75 cursor-not-allowed' : ''}`}
                >
                  {isRunning ? 'Running...' : 'Run Collection'}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Results Section */}
        <div className={themeClasses.section}>
          <div className="flex justify-between items-center mb-4">
            <h2 className={themeClasses.heading}>Run Results</h2>
            <div className="text-sm text-text-secondary">
              {runResults.length} requests completed
            </div>
          </div>
          
          {runResults.length === 0 ? (
            <div className="text-center py-8 text-text-secondary">
              <p>No results yet. Run your collection to see results here.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 px-3 font-medium">Request</th>
                    <th className="text-left py-2 px-3 font-medium">Status</th>
                    <th className="text-left py-2 px-3 font-medium">Time</th>
                    <th className="text-left py-2 px-3 font-medium">Response Code</th>
                  </tr>
                </thead>
                <tbody>
                  {runResults.map((result) => (
                    <tr key={result.id} className="border-b border-border last:border-b-0 hover:bg-surface-tertiary">
                      <td className="py-2 px-3">{result.name}</td>
                      <td className="py-2 px-3">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${result.status === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                          {result.status}
                        </span>
                      </td>
                      <td className="py-2 px-3">{result.time}</td>
                      <td className="py-2 px-3">{result.responseCode}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default RunnerTab;