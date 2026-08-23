import React from 'react';

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

declare const SelectionList: <T extends { id?: string | number }>(
  props: SelectionListProps<T>
) => React.ReactElement;

export default SelectionList;
