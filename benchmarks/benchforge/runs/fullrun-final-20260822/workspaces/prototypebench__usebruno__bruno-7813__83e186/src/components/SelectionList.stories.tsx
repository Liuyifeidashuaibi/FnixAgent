import React from 'react';
import { ComponentStory, ComponentMeta } from '@storybook/react';
import SelectionList from './SelectionList';

// Mock data for stories
interface TestItem {
  id: string;
  name: string;
  type: string;
}

const mockItems: TestItem[] = [
  { id: '1', name: 'API Collection', type: 'collection' },
  { id: '2', name: 'Development Environment', type: 'environment' },
  { id: '3', name: 'Login Request', type: 'request' },
  { id: '4', name: 'Test Collection', type: 'collection' },
  { id: '5', name: 'Production Environment', type: 'environment' },
];

const renderItem = (item: TestItem, isSelected: boolean, toggleItem: () => void) => (
  <div className="flex items-center p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
    <input
      type="checkbox"
      checked={isSelected}
      onChange={toggleItem}
      className="h-4 w-4 text-blue-600 rounded focus:ring-blue-500 mr-3"
    />
    <div className="flex-1 min-w-0">
      <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
        {item.name}
      </p>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {item.type}
      </p>
    </div>
  </div>
);

export default {
  title: 'Components/SelectionList',
  component: SelectionList,
  argTypes: {
    items: {
      control: { type: 'object' },
      description: 'Array of items to display'
    },
    renderItem: {
      control: { type: 'function' },
      description: 'Function to render each item'
    },
    visibleRows: {
      control: { type: 'number' },
      defaultValue: 5,
      description: 'Number of visible rows before scrolling'
    }
  }
} as ComponentMeta<typeof SelectionList>;

const Template: ComponentStory<typeof SelectionList> = (args) => <SelectionList {...args} />;

export const Default = Template.bind({});
Default.args = {
  items: mockItems,
  renderItem,
  visibleRows: 5
};

export const WithHeader = Template.bind({});
WithHeader.args = {
  items: mockItems,
  renderItem,
  renderHeader: () => (
    <div className="flex items-center justify-between">
      <h3 className="text-sm font-medium text-gray-900 dark:text-white">
        Select Items to Import
      </h3>
      <span className="text-xs text-gray-500 dark:text-gray-400">
        0 selected
      </span>
    </div>
  ),
  visibleRows: 3
};

export const EmptyState = Template.bind({});
EmptyState.args = {
  items: [],
  renderItem,
  emptyStateMessage: 'No import paths available',
  visibleRows: 5
};

export const SmallSpacing = Template.bind({});
SmallSpacing.args = {
  items: mockItems.slice(0, 3),
  renderItem,
  spacing: 'sm',
  visibleRows: 3
};
