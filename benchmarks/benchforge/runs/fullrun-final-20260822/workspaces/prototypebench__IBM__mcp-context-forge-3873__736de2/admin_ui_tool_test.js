// Admin UI Tool Testing Workflow
// New invokeTool(toolName) function called by "Invoke" buttons in Tools table
// Fetches tool details via API (fetchToolDetails) and populates modal dynamically
// Dynamic form generation from tool input schema (createFormInput, generateToolFormFields)

// Configuration for REST response truncation
const REST_RESPONSE_TEXT_MAX_LENGTH = 5000;

// Function to invoke a tool by name
class AdminUIToolTest {
  constructor() {
    this.toolsCache = new Map();
  }

  // Fetch tool details via API
  async fetchToolDetails(toolName) {
    try {
      const response = await fetch(`/api/tools/${toolName}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch tool details: ${response.status} ${response.statusText}`);
      }
      const toolDetails = await response.json();
      this.toolsCache.set(toolName, toolDetails);
      return toolDetails;
    } catch (error) {
      console.error('Error fetching tool details:', error);
      throw error;
    }
  }

  // Generate form input elements based on schema
  createFormInput(fieldName, fieldSchema, value = '') {
    const input = document.createElement('input');
    input.type = 'text';
    input.name = fieldName;
    input.value = value;
    
    // Set placeholder based on schema description
    if (fieldSchema.description) {
      input.placeholder = fieldSchema.description;
    }
    
    // Set type based on schema type
    if (fieldSchema.type === 'number') {
      input.type = 'number';
    } else if (fieldSchema.type === 'boolean') {
      input.type = 'checkbox';
      input.checked = value === true;
      input.value = 'true';
    }
    
    return input;
  }

  // Generate tool form fields from input schema
  generateToolFormFields(toolDetails) {
    const form = document.createElement('form');
    form.className = 'tool-form';
    
    if (!toolDetails.input_schema || !toolDetails.input_schema.properties) {
      const noInputs = document.createElement('p');
      noInputs.textContent = 'No input parameters required.';
      form.appendChild(noInputs);
      return form;
    }
    
    const properties = toolDetails.input_schema.properties;
    
    Object.entries(properties).forEach(([fieldName, fieldSchema]) => {
      const fieldDiv = document.createElement('div');
      fieldDiv.className = 'form-field';
      
      const label = document.createElement('label');
      label.textContent = fieldSchema.title || fieldName;
      label.htmlFor = fieldName;
      
      const input = this.createFormInput(fieldName, fieldSchema);
      
      fieldDiv.appendChild(label);
      fieldDiv.appendChild(input);
      
      form.appendChild(fieldDiv);
    });
    
    return form;
  }

  // Invoke tool by name - called by "Invoke" buttons
  async invokeTool(toolName) {
    try {
      // Fetch tool details
      const toolDetails = await this.fetchToolDetails(toolName);
      
      // Create and show modal
      const modal = this.createToolModal(toolName, toolDetails);
      document.body.appendChild(modal);
      
      // Populate form with dynamic fields
      const formContainer = modal.querySelector('.form-container');
      const form = this.generateToolFormFields(toolDetails);
      formContainer.appendChild(form);
      
      // Add event listener to form submission
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Collect form data
        const formData = new FormData(form);
        const argumentsObj = {};
        
        for (let [key, value] of formData.entries()) {
          // Handle checkbox values
          if (value === 'true') {
            argumentsObj[key] = true;
          } else if (value === 'false') {
            argumentsObj[key] = false;
          } else {
            argumentsObj[key] = value;
          }
        }
        
        // Run tool test with consistent structure
        await this.runToolTest(toolName, argumentsObj);
      });
      
    } catch (error) {
      console.error('Error invoking tool:', error);
      this.showErrorModal(`Failed to invoke tool ${toolName}: ${error.message}`);
    }
  }

  // Create tool invocation modal
  createToolModal(toolName, toolDetails) {
    const modal = document.createElement('div');
    modal.className = 'tool-modal';
    modal.innerHTML = `
      <div class="modal-content">
        <div class="modal-header">
          <h3>Invoke Tool: ${toolName}</h3>
          <button class="close-btn">&times;</button>
        </div>
        <div class="modal-body">
          <p>${toolDetails.description || 'No description available.'}</p>
          <div class="form-container"></div>
        </div>
        <div class="modal-footer">
          <button type="button" class="cancel-btn">Cancel</button>
          <button type="submit" class="invoke-btn">Invoke</button>
        </div>
      </div>
    `;
    
    // Add close functionality
    const closeBtn = modal.querySelector('.close-btn');
    const cancelBtn = modal.querySelector('.cancel-btn');
    
    [closeBtn, cancelBtn].forEach(btn => {
      btn.addEventListener('click', () => {
        modal.remove();
      });
    });
    
    return modal;
  }

  // Show error modal
  showErrorModal(message) {
    const modal = document.createElement('div');
    modal.className = 'error-modal';
    modal.innerHTML = `
      <div class="modal-content">
        <div class="modal-header">
          <h3>Error</h3>
          <button class="close-btn">&times;</button>
        </div>
        <div class="modal-body">
          <p>${message}</p>
        </div>
        <div class="modal-footer">
          <button class="ok-btn">OK</button>
        </div>
      </div>
    `;
    
    const closeBtn = modal.querySelector('.close-btn');
    const okBtn = modal.querySelector('.ok-btn');
    
    [closeBtn, okBtn].forEach(btn => {
      btn.addEventListener('click', () => {
        modal.remove();
      });
    });
    
    document.body.appendChild(modal);
  }

  // Run tool test with consistent tools/call method structure
  async runToolTest(toolName, argumentsObj) {
    try {
      const payload = {
        method: "tools/call",
        params: { 
          name: toolName, 
          arguments: argumentsObj 
        }
      };
      
      const response = await fetch('/api/tools/call', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) {
        throw new Error(`Tool execution failed: ${response.status} ${response.statusText}`);
      }
      
      const result = await response.json();
      
      // Show result modal
      this.showResultModal(toolName, result);
      
      return result;
    } catch (error) {
      console.error('Error running tool test:', error);
      this.showErrorModal(`Failed to execute tool ${toolName}: ${error.message}`);
      throw error;
    }
  }

  // Run tool validation
  async runToolValidation(toolName, argumentsObj) {
    try {
      const payload = {
        method: "tools/validate",
        params: { 
          name: toolName, 
          arguments: argumentsObj 
        }
      };
      
      const response = await fetch('/api/tools/validate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) {
        throw new Error(`Tool validation failed: ${response.status} ${response.statusText}`);
      }
      
      const result = await response.json();
      return result;
    } catch (error) {
      console.error('Error running tool validation:', error);
      throw error;
    }
  }

  // Show result modal
  showResultModal(toolName, result) {
    const modal = document.createElement('div');
    modal.className = 'result-modal';
    
    // Format result for display
    const resultString = JSON.stringify(result, null, 2);
    
    modal.innerHTML = `
      <div class="modal-content">
        <div class="modal-header">
          <h3>Tool Result: ${toolName}</h3>
          <button class="close-btn">&times;</button>
        </div>
        <div class="modal-body">
          <pre class="result-output">${resultString}</pre>
        </div>
        <div class="modal-footer">
          <button class="copy-btn">Copy Result</button>
          <button class="close-btn">Close</button>
        </div>
      </div>
    `;
    
    const closeBtns = modal.querySelectorAll('.close-btn');
    const copyBtn = modal.querySelector('.copy-btn');
    
    closeBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        modal.remove();
      });
    });
    
    copyBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(resultString);
      copyBtn.textContent = 'Copied!';
      setTimeout(() => {
        copyBtn.textContent = 'Copy Result';
      }, 2000);
    });
    
    document.body.appendChild(modal);
  }
}

// Initialize the admin UI tool test system
const adminToolTest = new AdminUIToolTest();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = adminToolTest;
}

// Make available globally for HTML button onclick handlers
window.adminToolTest = adminToolTest;

// Example usage for HTML buttons:
// <button onclick="adminToolTest.invokeTool('my-tool')">Invoke My Tool</button>
