import React, { useState, useEffect } from 'react';

interface SelectionListProps<T> {
  items: T[];
  renderItem: (item: T, isSelected: boolean, toggleItem: () => void) => React.ReactNode;
  renderHeader?: () => React.ReactNode;
  onSelectAll?: (selectAll: boolean) => void;
  selectedItems?: Set<T> | null;
  onSelectionChange?: (selectedItems: Set<T>) => void;
  visibleRows?: number;
  spacing?: 'sm' | 'md' | 'lg';
  emptyStateMessage?: string;
}

const SelectionList = <T extends { id?: string | number }>({ 
  items,
  renderItem,
  renderHeader,
  onSelectAll,
  selectedItems = null,
  onSelectionChange,
  visibleRows = 5,
  spacing = 'md',
  emptyStateMessage = 'No items available'
}: SelectionListProps<T>) => {
  const [localSelectedItems, setLocalSelectedItems] = useState<Set<T>>(new Set());
  const [selectAllChecked, setSelectAllChecked] = useState(false);
  
  // Use external selectedItems if provided, otherwise use local state
  const currentSelectedItems = selectedItems !== null ? selectedItems : localSelectedItems;
  
  useEffect(() => {
    // Update select all checkbox state based on current selections
    if (items.length > 0) {
      const allSelected = items.length > 0 && 
        Array.from(currentSelectedItems).every(item => 
          items.some(i => i.id === item.id || i === item)
        );
      setSelectAllChecked(allSelected);
    }
  }, [currentSelectedItems, items]);

  const toggleItem = (item: T) => {
    const newSelectedItems = new Set(currentSelectedItems);
    if (newSelectedItems.has(item)) {
      newSelectedItems.delete(item);
    } else {
      newSelectedItems.add(item);
    }
    
    if (selectedItems === null) {
      setLocalSelectedItems(newSelectedItems);
    }
    
    if (onSelectionChange) {
      onSelectionChange(newSelectedItems);
    }
  };

  const toggleSelectAll = () => {
    const newSelectAll = !selectAllChecked;
    const newSelectedItems = new Set<T>();
    
    if (newSelectAll) {
      items.forEach(item => newSelectedItems.add(item));
    }
    
    if (selectedItems === null) {
      setLocalSelectedItems(newSelectedItems);
    }
    
    if (onSelectionChange) {
      onSelectionChange(newSelectedItems);
    }
    
    if (onSelectAll) {
      onSelectAll(newSelectAll);
    }
  };

  const spacingClasses = {
    sm: 'space-y-1',
    md: 'space-y-2',
    lg: 'space-y-3'
  };

  return (
    <div className="selection-list-container">
      {/* Header with Select All */}
      {renderHeader && (
        <div className="selection-list-header mb-2">
          {renderHeader()}
        </div>
      )}
      
      {items.length === 0 ? (
        <div className="selection-list-empty text-center py-4 text-gray-500">
          {emptyStateMessage}
        </div>
      ) : (
        <div 
          className="selection-list-viewport overflow-y-auto"
          style={{ maxHeight: `${visibleRows * 48}px` }} // Assuming ~48px per item
        >
          <div className={`selection-list-items ${spacingClasses[spacing]}`}>
            {items.map((item, index) => {
              const isSelected = currentSelectedItems.has(item);
              return (
                <div 
                  key={item.id ?? index} 
                  className="selection-list-item"
                >
                  {renderItem(item, isSelected, () => toggleItem(item))}
                </div>
              );
            })}
          </div>
        </div>
      )}
      
      {/* Select All Footer */}
      {items.length > 0 && (
        <div className="selection-list-footer mt-3 pt-2 border-t border-gray-200">
          <label className="flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={selectAllChecked}
              onChange={toggleSelectAll}
              className="h-4 w-4 text-blue-600 rounded focus:ring-blue-500"
            />
            <span className="ml-2 text-sm font-medium text-gray-700">
              Select all ({items.length})
            </span>
          </label>
        </div>
      )}
    </div>
  );
};

export default SelectionList;
