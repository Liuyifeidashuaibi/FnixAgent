// Initialize the iframe with a default page
const iframe = document.querySelector('.content');
const addressSelect = document.querySelector('.address');
const readingTimeDisplay = document.querySelector('.reading-time');

// Function to normalize path
function normalizePath(path) {
    return path.startsWith('/') ? path : '/' + path;
}

// Function to update address select options
function updateAddressOptions() {
    const currentUrl = new URL(iframe.src);
    const path = currentUrl.pathname;
    const normalizedPath = normalizePath(path);
    
    // Update the address select value
    addressSelect.value = normalizedPath;
}

// Initial update
updateAddressOptions();

// Update on iframe load
iframe.addEventListener('load', () => {
    updateAddressOptions();
    console.log('Iframe loaded');
    updateReadingTime();
});

// Update address select when changed
addressSelect.addEventListener('change', () => {
    const newPath = addressSelect.value;
    iframe.src = newPath;
});

// Function to calculate and display reading time
function updateReadingTime() {
    const content = iframe.contentDocument.body.innerText;
    const words = content.split('\s').length;
    const readingSpeed = 200; // words per minute
    const timeInMinutes = words / readingSpeed;
    const timeInSeconds = Math.round(timeInMinutes * 60 * 10) / 10; // Rounded to one decimal place
    readingTimeDisplay.textContent = timeInSeconds;
}

// Listen for page changes and update reading time
iframe.addEventListener('load', updateReadingTime);

// Pause reading time when page is hidden
window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
        // Pause reading time calculation
    } else {
        // Resume reading time calculation
        updateReadingTime();
    }
});