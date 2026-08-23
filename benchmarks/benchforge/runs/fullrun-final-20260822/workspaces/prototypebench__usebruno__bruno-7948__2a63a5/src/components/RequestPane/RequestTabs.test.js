import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react';
import RequestTabs from './RequestTabs';

// Mock the component for testing
const mockRequests = [
  { id: 'req-1', name: 'GET /api/users' },
  { id: 'req-2', name: 'POST /api/users' },
  { id: 'req-3', name: 'PUT /api/users/1' }
];

describe('RequestTabs', () => {
  let onTabSelectMock;
  let onTabCloseMock;

  beforeEach(() => {
    onTabSelectMock = jest.fn();
    onTabCloseMock = jest.fn();
  });

  it('should select the correct tab when activeRequestId changes', () => {
    const { rerender, getByText } = render(
      <RequestTabs 
        requests={mockRequests} 
        activeRequestId="req-1" 
        onTabSelect={onTabSelectMock}
      />
    );

    // Check initial state
    expect(getByText('GET /api/users')).toHaveClass('active');

    // Rerender with different active request
    rerender(
      <RequestTabs 
        requests={mockRequests} 
        activeRequestId="req-2" 
        onTabSelect={onTabSelectMock}
      />
    );

    // Check that correct tab is now active
    expect(getByText('POST /api/users')).toHaveClass('active');
  });

  it('should call onTabSelect when tab is clicked', () => {
    const { getByText } = render(
      <RequestTabs 
        requests={mockRequests} 
        activeRequestId="req-1" 
        onTabSelect={onTabSelectMock}
      />
    );

    fireEvent.click(getByText('POST /api/users'));
    
    expect(onTabSelectMock).toHaveBeenCalledWith('req-2');
  });
});