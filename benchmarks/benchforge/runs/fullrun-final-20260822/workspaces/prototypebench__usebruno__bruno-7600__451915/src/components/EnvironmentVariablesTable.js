import React from 'react';
import { useSelector } from 'react-redux';

const EnvironmentVariablesTable = ({ collection, getAllVariables }) => {
  // Fix: when collection is null (global environment editor), 
  // read processEnvVariables directly from active workspace in Redux
  const processEnvVariables = collection === null 
    ? useSelector(state => state.workspaces?.activeWorkspace?.processEnvVariables || {}) 
    : {};

  // Enhanced getAllVariables to include process env variables when collection is null
  const getAllVariablesSafe = () => {
    if (collection === null) {
      // For global environment editor, include workspace process.env values
      return {
        ...getAllVariables?.() || {},
        ...processEnvVariables
      };
    }
    return getAllVariables?.() || {};
  };

  // Rest of the component implementation...
  
  return (
    <div>
      {/* Environment variables table UI */}
      <h3>Environment Variables</h3>
      <p>Collection: {collection ? collection.name : 'Global'}</p>
      <p>Process Env Variables: {Object.keys(processEnvVariables).length} variables</p>
      <p>Total Variables: {Object.keys(getAllVariablesSafe()).length}</p>
    </div>
  );
};

export default EnvironmentVariablesTable;