import { onTabClose, onAppBoot } from './brunoTabIntegration';

// Mock the utility functions
jest.mock('../utils', () => ({
  clearPersistedScope: jest.fn(),
  clearAllPersistedState: jest.fn(),
}));

// Import the mocked functions
const { clearPersistedScope, clearAllPersistedState } = require('../utils');

describe('Bruno Tab Integration', () => {
  beforeEach(() => {
    clearPersistedScope.mockClear();
    clearAllPersistedState.mockClear();
  });

  it('should clear persisted scope when tab is closed', () => {
    const tabUid = 'test-tab-123';
    
    onTabClose(tabUid);
    
    expect(clearPersistedScope).toHaveBeenCalledWith(tabUid);
  });

  it('should clear all persisted state on app boot', () => {
    onAppBoot();
    
    expect(clearAllPersistedState).toHaveBeenCalledTimes(1);
  });
});