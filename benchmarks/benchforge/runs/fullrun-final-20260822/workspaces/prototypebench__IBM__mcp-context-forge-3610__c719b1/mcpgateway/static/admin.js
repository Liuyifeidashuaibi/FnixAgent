// Manage Members Modal JavaScript

// Initialize the modal functionality
function initManageMembersModal() {
    // Current members section search
    const memberSearchInput = document.getElementById('member-search-input');
    const memberResultsContainer = document.getElementById('member-results-container');
    
    // Non-members section search
    const nonMemberSearchInput = document.getElementById('non-member-search-input');
    const nonMemberResultsContainer = document.getElementById('non-member-results-container');
    
    // Selection state preservation
    const selectedMembers = new Set();
    const selectedNonMembers = new Set();
    
    // Debounce function for search
    function debounce(func, wait) {
        let timeout;
        return function executedFunction() {
            const later = () => {
                clearTimeout(timeout);
                func(...arguments);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    // Server-side member search
    function serverSideMemberSearch(searchTerm) {
        if (!searchTerm || searchTerm.length < 2) {
            memberResultsContainer.innerHTML = '<p class="no-results">Enter at least 2 characters to search</p>';
            return;
        }
        
        fetch('/api/server-side-member-search/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                search: searchTerm
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                memberResultsContainer.innerHTML = `<p class="error">${data.error}</p>`;
                return;
            }
            
            // Render results and preserve selection state
            renderMembersResults(data.results, memberResultsContainer, selectedMembers);
        })
        .catch(error => {
            console.error('Member search error:', error);
            memberResultsContainer.innerHTML = '<p class="error">Search failed. Please try again.</p>';
        });
    }
    
    // Server-side non-member search
    function serverSideNonMemberSearch(searchTerm) {
        if (!searchTerm || searchTerm.length < 2) {
            nonMemberResultsContainer.innerHTML = '<p class="no-results">Enter at least 2 characters to search</p>';
            return;
        }
        
        fetch('/api/server-side-non-member-search/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                search: searchTerm
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                nonMemberResultsContainer.innerHTML = `<p class="error">${data.error}</p>`;
                return;
            }
            
            // Render results and preserve selection state
            renderNonMembersResults(data.results, nonMemberResultsContainer, selectedNonMembers);
        })
        .catch(error => {
            console.error('Non-member search error:', error);
            nonMemberResultsContainer.innerHTML = '<p class="error">Search failed. Please try again.</p>';
        });
    }
    
    // Render members results with selection state preservation
    function renderMembersResults(results, container, selectedSet) {
        if (results.length === 0) {
            container.innerHTML = '<p class="no-results">No members found</p>';
            return;
        }
        
        const html = results.map(user => {
            const isChecked = selectedSet.has(user.id);
            return `
                <div class="member-item">
                    <label>
                        <input type="checkbox" 
                               name="selected_members" 
                               value="${user.id}" 
                               ${isChecked ? 'checked' : ''}>
                        ${user.username || user.email} (${user.email})
                    </label>
                </div>
            `;
        }).join('');
        
        container.innerHTML = html;
    }
    
    // Render non-members results with selection state preservation
    function renderNonMembersResults(results, container, selectedSet) {
        if (results.length === 0) {
            container.innerHTML = '<p class="no-results">No non-members found</p>';
            return;
        }
        
        const html = results.map(user => {
            const isChecked = selectedSet.has(user.id);
            return `
                <div class="non-member-item">
                    <label>
                        <input type="checkbox" 
                               name="selected_non_members" 
                               value="${user.id}" 
                               ${isChecked ? 'checked' : ''}>
                        ${user.username || user.email} (${user.email})
                    </label>
                </div>
            `;
        }).join('');
        
        container.innerHTML = html;
    }
    
    // Get CSRF token from cookie
    function getCSRFToken() {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.startsWith('csrftoken=')) {
                return cookie.substring('csrftoken='.length, cookie.length);
            }
        }
        return '';
    }
    
    // Event listeners for search inputs
    if (memberSearchInput) {
        memberSearchInput.addEventListener('input', debounce((e) => {
            serverSideMemberSearch(e.target.value);
        }, 300));
    }
    
    if (nonMemberSearchInput) {
        nonMemberSearchInput.addEventListener('input', debounce((e) => {
            serverSideNonMemberSearch(e.target.value);
        }, 300));
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initManageMembersModal();
});