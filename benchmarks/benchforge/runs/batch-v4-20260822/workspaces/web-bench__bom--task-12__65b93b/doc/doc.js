// doc/doc.js — ES module for documentation pages
// Provides: side navigation menu with click-to-hide behavior

/**
 * Initialize the documentation menu.
 * - Creates a side menu if not already present
 * - Clicking anywhere on the doc page (outside the menu) hides the menu
 * - A toggle button can show/hide the menu
 */
export function initMenu() {
    const menu = document.getElementById('doc-menu');
    if (!menu) return;

    // Create toggle button if not present
    let toggleBtn = document.getElementById('doc-menu-toggle');
    if (!toggleBtn) {
        toggleBtn = document.createElement('button');
        toggleBtn.id = 'doc-menu-toggle';
        toggleBtn.textContent = '☰';
        toggleBtn.setAttribute('aria-label', 'Toggle menu');
        document.body.prepend(toggleBtn);
    }

    // Toggle menu via button
    toggleBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        menu.classList.toggle('hidden');
    });

    // Click anywhere on the doc page to hide the menu
    document.addEventListener('click', function (e) {
        if (!menu.contains(e.target) && e.target !== toggleBtn) {
            menu.classList.add('hidden');
        }
    });

    // Prevent clicks inside the menu from hiding it
    menu.addEventListener('click', function (e) {
        e.stopPropagation();
    });
}

// Auto-initialize when the module is imported
document.addEventListener('DOMContentLoaded', initMenu);
