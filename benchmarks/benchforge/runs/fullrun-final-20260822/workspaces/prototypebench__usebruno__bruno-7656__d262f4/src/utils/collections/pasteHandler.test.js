import { handlePasteItem, shouldShowPasteMenu, getPasteMenuLabel } from './pasteHandler';

// Mock clipboard for testing
const mockClipboard = {
  readText: jest.fn(),
  availableFormats: jest.fn(),
  read: jest.fn()
};

// Mock electron clipboard
jest.mock('electron', () => ({
  clipboard: mockClipboard
}));

describe('pasteHandler', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('shouldShowPasteMenu', () => {
    it('should return true for folders', () => {
      const folder = { type: 'folder', id: '1' };
      expect(shouldShowPasteMenu(folder)).toBe(true);
    });

    it('should return true for requests', () => {
      const request = { type: 'request', id: '2' };
      expect(shouldShowPasteMenu(request)).toBe(true);
    });

    it('should return false for null or undefined', () => {
      expect(shouldShowPasteMenu(null)).toBe(false);
      expect(shouldShowPasteMenu(undefined)).toBe(false);
    });
  });

  describe('getPasteMenuLabel', () => {
    it('should return "Paste Inside" for folders', () => {
      const folder = { type: 'folder', id: '1' };
      expect(getPasteMenuLabel(folder)).toBe('Paste Inside');
    });

    it('should return "Paste" for requests', () => {
      const request = { type: 'request', id: '2' };
      expect(getPasteMenuLabel(request)).toBe('Paste');
    });

    it('should return "Paste" for null or undefined', () => {
      expect(getPasteMenuLabel(null)).toBe('Paste');
      expect(getPasteMenuLabel(undefined)).toBe('Paste');
    });
  });

  describe('handlePasteItem', () => {
    it('should paste inside folder when focused on folder', async () => {
      const focusedFolder = { type: 'folder', id: 'folder-1', parentId: 'root' };
      const onPasteMock = jest.fn();
      
      mockClipboard.readText.mockReturnValue('{"type":"request","name":"Test"}');
      
      await handlePasteItem(focusedFolder, onPasteMock);
      
      expect(onPasteMock).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'request', name: 'Test' }),
        expect.objectContaining({ target: 'inside', folderId: 'folder-1' })
      );
    });

    it('should paste as sibling when focused on request', async () => {
      const focusedRequest = { type: 'request', id: 'req-1', parentId: 'folder-1' };
      const onPasteMock = jest.fn();
      
      mockClipboard.readText.mockReturnValue('{"type":"request","name":"Test"}');
      
      await handlePasteItem(focusedRequest, onPasteMock);
      
      expect(onPasteMock).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'request', name: 'Test' }),
        expect.objectContaining({ target: 'sibling', parentId: 'folder-1' })
      );
    });

    it('should handle plain text clipboard content', async () => {
      const focusedFolder = { type: 'folder', id: 'folder-1' };
      const onPasteMock = jest.fn();
      
      mockClipboard.readText.mockReturnValue('Plain text content');
      
      await handlePasteItem(focusedFolder, onPasteMock);
      
      expect(onPasteMock).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'request', name: 'Pasted Request', content: 'Plain text content' }),
        expect.objectContaining({ target: 'inside', folderId: 'folder-1' })
      );
    });
  });
});