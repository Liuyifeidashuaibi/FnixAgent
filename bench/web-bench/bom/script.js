const backBtn = document.querySelector('.back');
const forwardBtn = document.querySelector('.forward');
const homepageBtn = document.querySelector('.homepage');
const refreshBtn = document.querySelector('.refresh');
const contentIframe = document.querySelector('.content');
const themeSelect = document.querySelector('.theme');

// Navigation history
let history = [];
let currentIndex = -1;

// Function to update button states
function updateButtonStates() {
    backBtn.disabled = currentIndex <= 0;
    forwardBtn.disabled = currentIndex >= history.length - 1;
}

// Function to load a URL in the iframe
function loadUrl(url) {
    if (url && url !== '') {
        contentIframe.src = url;
        // Update history
        if (currentIndex < history.length - 1) {
            history = history.slice(0, currentIndex + 1);
        }
        history.push(url);
        currentIndex++;
        updateButtonStates();
    }
}

// Theme management
function setTheme(theme) {
    // Set body class
    document.body.className = theme;
    
    // Save to localStorage
    localStorage.setItem('theme', theme);
    
    // Apply theme to doc pages
    if (contentIframe.contentDocument && contentIframe.contentDocument.body) {
        contentIframe.contentDocument.body.className = theme;
    }
    
    // Listen for messages from doc pages to sync theme
    window.addEventListener('message', function(event) {
        if (event.data.type === 'sync-theme') {
            if (contentIframe.contentDocument && contentIframe.contentDocument.body) {
                contentIframe.contentDocument.body.className = theme;
            }
        }
    });
}

// Initialize theme
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.body.className = savedTheme;
    
    // Set select value
    if (themeSelect) {
        themeSelect.value = savedTheme;
    }
    
    // Apply theme to current doc page if loaded
    if (contentIframe.contentDocument && contentIframe.contentDocument.body) {
        contentIframe.contentDocument.body.className = savedTheme;
    }
}

// Theme change handler
if (themeSelect) {
    themeSelect.addEventListener('change', function() {
        const selectedTheme = this.value;
        setTheme(selectedTheme);
        
        // Send message to doc pages to update their theme
        if (contentIframe.contentDocument) {
            contentIframe.contentDocument.postMessage({
                type: 'set-theme',
                theme: selectedTheme
            }, '*');
        }
    });
}

// Homepage button click handler
homepageBtn.addEventListener('click', () => {
    loadUrl('docs/intro.html');
});

// Back button click handler
backBtn.addEventListener('click', () => {
    if (currentIndex > 0) {
        currentIndex--;
        loadUrl(history[currentIndex]);
    }
});

// Forward button click handler
forwardBtn.addEventListener('click', () => {
    if (currentIndex < history.length - 1) {
        currentIndex++;
        loadUrl(history[currentIndex]);
    }
});

// Refresh button click handler
refreshBtn.addEventListener('click', () => {
    if (currentIndex >= 0 && currentIndex < history.length) {
        loadUrl(history[currentIndex]);
    }
});

// Initial state
updateButtonStates();
initTheme();