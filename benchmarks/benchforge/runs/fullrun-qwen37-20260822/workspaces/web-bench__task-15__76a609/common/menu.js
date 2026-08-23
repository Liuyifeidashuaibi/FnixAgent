/**
 * Menu system with delete shortcut support.
 * Menu item 'delete' is displayed and can be triggered via:
 *   - Click on the menu item
 *   - Pressing 'Delete' or 'Backspace' key
 */
(function () {
  'use strict';

  // ─── State ────────────────────────────────────────────────────────
  var clipboard = { type: null, data: null };
  var selectedItems = [];
  var panelType = 'entry';

  // ─── Helpers ──────────────────────────────────────────────────────

  function showToast(msg) {
    if (typeof window.showNotification === 'function') {
      window.showNotification(msg);
    } else {
      console.log('[menu]', msg);
    }
  }

  function refreshPanel() {
    if (typeof window.refreshPanel === 'function') {
      window.refreshPanel(panelType);
    }
  }

  // ─── Clipboard ────────────────────────────────────────────────────

  function doCopy(items) {
    if (!items || items.length === 0) return;
    clipboard.type = panelType;
    clipboard.data = JSON.parse(JSON.stringify(items));
    showToast('Entry copied.');
  }

  function doPaste(targetEl) {
    if (!clipboard.type) {
      showToast('Clipboard is empty.');
      return;
    }
    var items = Array.isArray(clipboard.data) ? clipboard.data : [clipboard.data];
    if (typeof window.onPasteItems === 'function') {
      window.onPasteItems(items, panelType, targetEl);
    } else if (typeof window.appendEntries === 'function') {
      window.appendEntries(items, panelType);
    }
    showToast('Entry pasted.');
  }

  function doCut(items) {
    if (!items || items.length === 0) return;
    doCopy(items);
    if (typeof window.removeEntries === 'function') {
      window.removeEntries(items, panelType);
    }
    showToast('Entry cut.');
  }

  // ─── Delete ───────────────────────────────────────────────────────

  /**
   * Delete handler – removes selected items permanently.
   * Called by both menu click and keyboard shortcuts (Delete / Backspace).
   */
  function onDelete(items) {
    if (!items || items.length === 0) return;
    var count = items.length;

    if (typeof window.confirmAction === 'function') {
      window.confirmAction(
        'Delete ' + count + ' item(s)?',
        function () {
          _removeAndNotify(items, count);
        }
      );
    } else {
      _removeAndNotify(items, count);
    }
  }

  function _removeAndNotify(items, count) {
    if (typeof window.removeEntries === 'function') {
      window.removeEntries(items, panelType);
    }
    showToast(count + ' item(s) deleted.');
    refreshPanel();
  }

  // ─── Rename ───────────────────────────────────────────────────────

  function onRename(id) {
    if (!id) {
      showToast('No item selected.');
      return;
    }
    var newName = prompt('Enter new name:');
    if (newName && newName.trim()) {
      if (typeof window.renameEntry === 'function') {
        window.renameEntry(id, newName.trim(), panelType);
      }
      showToast('Renamed.');
      refreshPanel();
    }
  }

  // ─── Duplicate ────────────────────────────────────────────────────

  function onDuplicate(items) {
    if (!items || items.length === 0) return;
    if (typeof window.duplicateEntries === 'function') {
      window.duplicateEntries(items, panelType);
    }
    showToast('Duplicated.');
    refreshPanel();
  }

  // ─── Select All ───────────────────────────────────────────────────

  function onSelectAll() {
    if (typeof window.selectAllInPanel === 'function') {
      window.selectAllInPanel(panelType);
    }
  }

  // ─── Context Menu Builder ─────────────────────────────────────────

  function buildContextMenu(opts) {
    opts = opts || {};
    panelType = opts.panelType || 'entry';
    selectedItems = opts.items || [];
    var count = selectedItems.length;

    var menu = document.createElement('div');
    menu.className = 'context-menu';
    menu.style.position = 'absolute';
    menu.style.zIndex = '9999';
    menu.style.background = '#fff';
    menu.style.border = '1px solid #ccc';
    menu.style.boxShadow = '0 2px 8px rgba(0,0,0,.15)';
    menu.style.borderRadius = '4px';
    menu.style.padding = '4px 0';
    menu.style.minWidth = '180px';
    menu.style.fontFamily = 'sans-serif';
    menu.style.fontSize = '13px';

    function addLink(text, className, handler) {
      var a = document.createElement('a');
      a.href = '#';
      a.className = 'context-menu-item ' + className;
      a.textContent = text;

      // Show shortcut hint
      if (className === 'menu-item-delete') {
        a.textContent += ' \u2014 Del / Backspace';
      }

      a.addEventListener('click', function (e) {
        e.preventDefault();
        handler();
      });
      menu.appendChild(a);
    }

    // Copy
    if (count > 0) {
      addLink('Copy', 'menu-item-copy', function () { doCopy(selectedItems); });
    }

    // Cut
    if (count > 0) {
      addLink('Cut', 'menu-item-cut', function () { doCut(selectedItems); });
    }

    // Paste
    if (clipboard.type) {
      addLink('Paste', 'menu-item-paste', function () { doPaste(null); });
    }

    // Separator
    var sep1 = document.createElement('div');
    sep1.className = 'context-menu-separator';
    sep1.style.borderTop = '1px solid #eee';
    sep1.style.margin = '4px 0';
    menu.appendChild(sep1);

    // Duplicate
    if (count > 0) {
      addLink('Duplicate', 'menu-item-duplicate', function () { onDuplicate(selectedItems); });
    }

    // Rename (single item only)
    if (count === 1 && selectedItems[0] && selectedItems[0].id) {
      addLink('Rename', 'menu-item-rename', function () { onRename(selectedItems[0].id); });
    }

    // Delete
    if (count > 0) {
      addLink('Delete', 'menu-item-delete', function () { onDelete(selectedItems); });
    }

    // Separator
    var sep2 = document.createElement('div');
    sep2.className = 'context-menu-separator';
    sep2.style.borderTop = '1px solid #eee';
    sep2.style.margin = '4px 0';
    menu.appendChild(sep2);

    // Select All
    addLink('Select All', 'menu-item-select-all', function () { onSelectAll(); });

    return menu;
  }

  // ─── Keyboard Shortcut Handler ────────────────────────────────────

  function onKeyDown(event) {
    var key = event.key;

    // Only handle Delete or Backspace when appropriate
    if (key === 'Delete' || key === 'Backspace') {
      // Don't intercept in input/textarea elements
      var tag = event.target.tagName.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || event.target.isContentEditable) {
        return;
      }

      // If there are selected items, delete them
      if (selectedItems && selectedItems.length > 0) {
        event.preventDefault();
        event.stopPropagation();
        onDelete(selectedItems);
      }
    }
  }

  // ─── Public API ───────────────────────────────────────────────────

  window.MenuActions = {
    /** Attach context-menu listener to a container. */
    attach: function (container, pType, getItemsFn) {
      panelType = pType || 'entry';

      container.addEventListener('contextmenu', function (e) {
        e.preventDefault();
        var items = getItemsFn ? getItemsFn() : [];
        selectedItems = items;
        var ctxMenu = buildContextMenu({ panelType: panelType, items: items });
        ctxMenu.style.left = e.pageX + 'px';
        ctxMenu.style.top = e.pageY + 'px';
        document.body.appendChild(ctxMenu);

        // Close on outside click
        setTimeout(function () {
          function closeHandler() {
            if (ctxMenu.parentNode) {
              ctxMenu.parentNode.removeChild(ctxMenu);
            }
            document.removeEventListener('click', closeHandler);
          }
          document.addEventListener('click', closeHandler);
        }, 0);
      });
    },

    /** Set selected items manually (for keyboard shortcut use). */
    setSelectedItems: function (items) {
      selectedItems = items || [];
    },

    /** Get selected items. */
    getSelectedItems: function () {
      return selectedItems;
    },

    /** Trigger delete on current selection. */
    deleteSelected: function () {
      if (selectedItems && selectedItems.length > 0) {
        onDelete(selectedItems);
      }
    },

    /** Build & return a context-menu DOM node. */
    buildContextMenu: buildContextMenu,

    /** Directly trigger copy. */
    copy: doCopy,

    /** Directly trigger paste. */
    paste: doPaste,

    /** Clear clipboard. */
    clearClipboard: function () {
      clipboard.type = null;
      clipboard.data = null;
    },

    /** Check if clipboard has data. */
    hasClipboard: function () {
      return clipboard.type !== null;
    },

    /** Register global keydown listener for Delete/Backspace shortcuts. */
    initKeyboardShortcuts: function () {
      document.addEventListener('keydown', onKeyDown, false);
    },

    /** Unregister global keydown listener. */
    destroyKeyboardShortcuts: function () {
      document.removeEventListener('keydown', onKeyDown, false);
    }
  };

  // Auto-initialize keyboard shortcuts on load
  window.MenuActions.initKeyboardShortcuts();

})();
