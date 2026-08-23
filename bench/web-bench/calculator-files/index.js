const display = document.getElementById('display');
const buttons = document.querySelectorAll('.btn');
const clearBtn = document.getElementById('clear');
const sqrtBtn = document.getElementById('sqrt');
const squareBtn = document.getElementById('square');
const reciprocalBtn = document.getElementById('reciprocal');
const sinBtn = document.getElementById('sin');
const piBtn = document.getElementById('pi');
const toggleBtn = document.getElementById('toggle');

let currentInput = '';

// Handle digit and operator button clicks
buttons.forEach(button => {
    button.addEventListener('click', () => {
        const value = button.dataset.value;
        
        if (value === '=') {
            calculate();
        } else {
            currentInput += value;
            display.value = currentInput;
        }
    });
});

// Calculate the result
function calculate() {
    try {
        if (currentInput === '' || currentInput === undefined) {
            display.value = 'Error';
            currentInput = '';
            return;
        }
        
        // Evaluate the expression
        const result = eval(currentInput);
        
        // Check if result is undefined or NaN
        if (result === undefined || isNaN(result)) {
            display.value = 'Error';
        } else {
            display.value = result;
            currentInput = result.toString();
        }
    } catch (error) {
        display.value = 'Error';
        currentInput = '';
    }
}

// Clear the display
clearBtn.addEventListener('click', () => {
    currentInput = '';
    display.value = '';
});

// Calculate square root
sqrtBtn.addEventListener('click', () => {
    try {
        const currentValue = parseFloat(display.value);
        if (isNaN(currentValue)) {
            display.value = 'Error';
            currentInput = '';
            return;
        }
        if (currentValue < 0) {
            display.value = 'Error';
            currentInput = '';
            return;
        }
        const result = Math.sqrt(currentValue);
        display.value = result;
        currentInput = result.toString();
    } catch (error) {
        display.value = 'Error';
        currentInput = '';
    }
});

// Calculate square
squareBtn.addEventListener('click', () => {
    try {
        const currentValue = parseFloat(display.value);
        if (isNaN(currentValue)) {
            display.value = 'Error';
            currentInput = '';
            return;
        }
        const result = currentValue * currentValue;
        display.value = result;
        currentInput = result.toString();
    } catch (error) {
        display.value = 'Error';
        currentInput = '';
    }
});

// Calculate reciprocal
reciprocalBtn.addEventListener('click', () => {
    try {
        const currentValue = parseFloat(display.value);
        if (isNaN(currentValue)) {
            display.value = 'Error';
            currentInput = '';
            return;
        }
        if (currentValue === 0) {
            display.value = 'Error';
            currentInput = '';
            return;
        }
        const result = 1 / currentValue;
        display.value = result;
        currentInput = result.toString();
    } catch (error) {
        display.value = 'Error';
        currentInput = '';
    }
});

// Calculate sine
sinBtn.addEventListener('click', () => {
    try {
        const currentValue = parseFloat(display.value);
        if (isNaN(currentValue)) {
            display.value = 'Error';
            currentInput = '';
            return;
        }
        // Convert degrees to radians for Math.sin
        const radians = currentValue * (Math.PI / 180);
        const result = Math.sin(radians);
        display.value = result;
        currentInput = result.toString();
    } catch (error) {
        display.value = 'Error';
        currentInput = '';
    }
});

// Set pi value
piBtn.addEventListener('click', () => {
    display.value = Math.PI;
    currentInput = Math.PI.toString();
});

// Theme toggle functionality
toggleBtn.addEventListener('click', () => {
    const body = document.body;
    const isDarkMode = body.classList.contains('dark-mode');
    
    if (isDarkMode) {
        body.classList.remove('dark-mode');
        toggleBtn.textContent = 'dark';
    } else {
        body.classList.add('dark-mode');
        toggleBtn.textContent = 'light';
    }
});

// Keyboard support
document.addEventListener('keydown', (e) => {
    const key = e.key;
    
    if (/[0-9]/.test(key) || ['+', '-', '*', '/', '.'].includes(key)) {
        currentInput += key;
        display.value = currentInput;
    } else if (key === 'Enter' || key === '=') {
        calculate();
    } else if (key === 'Escape' || key === 'c' || key === 'C') {
        currentInput = '';
        display.value = '';
    }
});