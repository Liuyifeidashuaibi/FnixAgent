import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import SelectionList from './SelectionList';

// Mock data for testing
interface TestItem {
  id: string;
  name: string;
}

const mockItems: TestItem[] = [
  { id: '1', name: 'Collection A' },
  { id: '2', name: 'Collection B' },
  { id: '3', name: 'Environment C' },
];

const renderItem = (item: TestItem, isSelected: boolean, toggleItem: () => void) => (
  <div>
    <input
      type="checkbox"
      checked={isSelected}
      onChange={toggleItem}
    />
    <span>{item.name}</span>
  </div>
);

describe('SelectionList', () => {
  it('renders items correctly', () => {
    render(
      <SelectionList
        items={mockItems}
        renderItem={renderItem}
      />
    );
    
    expect(screen.getByText('Collection A')).toBeInTheDocument();
    expect(screen.getByText('Collection B')).toBeInTheDocument();
    expect(screen.getByText('Environment C')).toBeInTheDocument();
  });

  it('handles select all functionality', () => {
    const onSelectionChange = jest.fn();
    
    render(
      <SelectionList
        items={mockItems}
        renderItem={renderItem}
        onSelectionChange={onSelectionChange}
      />
    );
    
    // Find and click select all checkbox
    const selectAllCheckbox = screen.getByLabelText('Select all (3)');
    fireEvent.click(selectAllCheckbox);
    
    expect(onSelectionChange).toHaveBeenCalledTimes(1);
  });
});
