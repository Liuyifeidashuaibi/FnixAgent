import React, { useState } from 'react';
import SelectionList from './SelectionList';

// Example usage for bulk import paths
interface ImportPath {
  id: string;
  path: string;
  type: 'collection' | 'environment' | 'request';
}

const BulkImportExample = () => {
  const [selectedPaths, setSelectedPaths] = useState<Set<ImportPath>>(new Set());
  
  const importPaths: ImportPath[] = [
    { id: '1', path: 'collections/api-collection.json', type: 'collection' },
    { id: '2', path: 'environments/dev.env.json', type: 'environment' },
    { id: '3', path: 'requests/login-request.json', type: 'request' },
    { id: '4', path: 'collections/test-collection.json', type: 'collection' },
    { id: '5', path: 'environments/prod.env.json', type: 'environment' },
  ];

  const renderItem = (item: ImportPath, isSelected: boolean, toggleItem: () => void) => (
    <div className="flex items-center p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
      <input
        type="checkbox"
        checked={isSelected}
        onChange={toggleItem}
        className="h-4 w-4 text-blue-600 rounded focus:ring-blue-500 mr-3"
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
          {item.path}
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {item.type}
        </p>
      </div>
    </div>
  );

  const renderHeader = () => (
    <div className="flex items-center justify-between">
      <h3 className="text-sm font-medium text-gray-900 dark:text-white">
        Select Items to Import
      </h3>
      <span className="text-xs text-gray-500 dark:text-gray-400">
        {selectedPaths.size} selected
      </span>
    </div>
  );

  return (
    <div className="max-w-2xl mx-auto p-4">
      <h2 className="text-lg font-semibold mb-4">Bulk Import Paths</h2>
      <SelectionList
        items={importPaths}
        renderItem={renderItem}
        renderHeader={renderHeader}
        selectedItems={selectedPaths}
        onSelectionChange={setSelectedPaths}
        visibleRows={5}
        spacing="md"
        emptyStateMessage="No import paths available"
      />
    </div>
  );
};

export default BulkImportExample;
