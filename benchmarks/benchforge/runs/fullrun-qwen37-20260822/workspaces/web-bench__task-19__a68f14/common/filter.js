/**
 * Filter Button Module for Tools Panel
 * Adds a filter button that prompts for a keyword and filters entry names.
 */

(function () {
  'use strict';

  // --- State ---
  const state = {
    keyword: '',
    filteredEntries: [],
    originalEntries: [],
    onChangeCallbacks: [],
  };

  // --- DOM Helpers ---
  function createElement(tag, attrs, children) {
    const el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach((key) => {
        if (key === 'className') {
          el.className = attrs[key];
        } else if (key.startsWith('on')) {
          el.addEventListener(key.slice(2).toLowerCase(), attrs[key]);
        } else {
          el.setAttribute(key, attrs[key]);
        }
      });
    }
    if (children) {
      if (Array.isArray(children)) {
        children.forEach((child) => {
          if (typeof child === 'string') {
            el.appendChild(document.createTextNode(child));
          } else {
            el.appendChild(child);
          }
        });
      } else if (typeof children === 'string') {
        el.appendChild(document.createTextNode(children));
      } else {
        el.appendChild(children);
      }
    }
    return el;
  }

  // --- Inject Styles ---
  function injectStyles() {
    if (document.getElementById('tool-filter-styles')) return;

    const style = document.createElement('style');
    style.id = 'tool-filter-styles';
    style.textContent = `
      /* Tools Panel Filter Section */
      .tool-filter-section {
        display: flex;
        gap: 6px;
        padding: 8px;
        background: var(--surface, #f5f5f5);
        border-bottom: 1px solid var(--border, #ddd);
        align-items: center;
      }

      .tool-filter-btn {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 6px 12px;
        font-size: 13px;
        font-weight: 500;
        color: var(--text-primary, #333);
        background: var(--surface-light, #fff);
        border: 1px solid var(--border, #ccc);
        border-radius: 4px;
        cursor: pointer;
        transition: all 0.2s ease;
        white-space: nowrap;
      }

      .tool-filter-btn:hover {
        background: var(--brand, #4a90d9);
        color: #fff;
        border-color: var(--brand, #4a90d9);
      }

      .tool-filter-btn.active {
        background: var(--brand, #4a90d9);
        color: #fff;
        border-color: var(--brand, #4a90d9);
      }

      .tool-clear-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        font-size: 14px;
        line-height: 1;
        color: var(--text-primary, #666);
        background: transparent;
        border: 1px solid var(--border, #ccc);
        border-radius: 4px;
        cursor: pointer;
        transition: all 0.2s ease;
      }

      .tool-clear-btn:hover {
        background: #e74c3c;
        color: #fff;
        border-color: #e74c3c;
      }

      .tool-clear-btn.hidden {
        display: none;
      }

      .tool-filter-status {
        font-size: 12px;
        color: var(--text-secondary, #888);
        margin-left: auto;
      }

      .tool-entry {
        padding: 8px 12px;
        cursor: pointer;
        transition: background 0.15s ease;
      }

      .tool-entry:hover {
        background: rgba(74, 144, 217, 0.1);
      }

      .tool-entry.filtered-out {
        display: none;
      }
    `;
    document.head.appendChild(style);
  }

  // --- Filter Button ---
  function createFilterButton() {
    injectStyles();

    const section = createElement('div', { className: 'tool-filter-section' });

    const filterBtn = createElement('button', {
      className: 'tool-filter-btn',
      title: 'Filter entries by keyword',
      innerText: '🔍 Filter',
    });

    filterBtn.addEventListener('click', handleFilterClick);

    const clearBtn = createElement('button', {
      className: 'tool-clear-btn hidden',
      title: 'Clear filter',
      innerText: '✕',
    });

    clearBtn.addEventListener('click', handleClearClick);

    const statusSpan = createElement('span', {
      className: 'tool-filter-status',
    });

    section.appendChild(filterBtn);
    section.appendChild(clearBtn);
    section.appendChild(statusSpan);

    // Store references for updates
    filterBtn._filterBtn = filterBtn;
    clearBtn._clearBtn = clearBtn;
    statusSpan._statusSpan = statusSpan;

    return { section, filterBtn, clearBtn, statusSpan };
  }

  function handleFilterClick() {
    const keyword = prompt('Enter keyword to filter entries:');

    if (keyword !== null) {
      applyFilter(keyword.trim());
    }
  }

  function handleClearClick() {
    clearFilter();
  }

  // --- Filtering Logic ---
  function setOriginalEntries(entries) {
    state.originalEntries = entries || [];
    state.filteredEntries = entries ? [...entries] : [];
    renderStatus();
    notifyChange();
  }

  function applyFilter(keyword) {
    state.keyword = keyword;

    if (!state.keyword || !state.originalEntries.length) {
      state.filteredEntries = state.originalEntries;
    } else {
      const lowerKeyword = state.keyword.toLowerCase();
      state.filteredEntries = state.originalEntries.filter((entry) => {
        const name = typeof entry === 'string' ? entry : entry.name || '';
        return name.toLowerCase().includes(lowerKeyword);
      });
    }

    updateUI();
    notifyChange();
  }

  function clearFilter() {
    state.keyword = '';
    state.filteredEntries = state.originalEntries;
    updateUI();
    notifyChange();
  }

  function updateUI() {
    const filterBtn = document.querySelector('.tool-filter-btn');
    const clearBtn = document.querySelector('.tool-clear-btn');
    const statusSpan = document.querySelector('.tool-filter-status');

    if (filterBtn) {
      filterBtn.classList.toggle('active', !!state.keyword);
    }

    if (clearBtn) {
      clearBtn.classList.toggle('hidden', !state.keyword);
    }

    if (statusSpan) {
      if (state.keyword && state.originalEntries.length > 0) {
        statusSpan.textContent = `${state.filteredEntries.length} of ${state.originalEntries.length} entries`;
      } else {
        statusSpan.textContent = '';
      }
    }
  }

  function renderStatus() {
    updateUI();
  }

  // --- Callbacks ---
  function onChange(callback) {
    state.onChangeCallbacks.push(callback);
  }

  function notifyChange() {
    state.onChangeCallbacks.forEach((cb) => {
      try {
        cb(state.filteredEntries, state.keyword);
      } catch (e) {
        console.error('[filter] callback error:', e);
      }
    });
  }

  // --- Public API ---
  window.FilterModule = {
    /** Create and return the filter button element */
    createButton: createFilterButton,

    /** Set the original list of entries to filter against */
    setEntries: setOriginalEntries,

    /** Apply a keyword filter (also called internally by the button) */
    filter: applyFilter,

    /** Clear current filter and show all entries */
    clear: clearFilter,

    /** Get current filtered results */
    getFilteredEntries: () => state.filteredEntries,

    /** Get current keyword */
    getKeyword: () => state.keyword,

    /** Register callback fired whenever filter changes */
    onChange: onChange,

    /** Internal state object */
    get state: () => state,
  };

})();
