class Calculator {
    constructor(previousOperandEl, currentOperandEl) {
        this.previousOperandEl = previousOperandEl;
        this.currentOperandEl = currentOperandEl;
        this.clear();
    }

    clear() {
        this.currentOperand = '0';
        this.previousOperand = '';
        this.operation = undefined;
    }

    delete() {
        if (this.currentOperand === 'Error') {
            this.clear();
            return;
        }
        this.currentOperand = this.currentOperand.toString().slice(0, -1);
        if (this.currentOperand === '' || this.currentOperand === '-') {
            this.currentOperand = '0';
        }
    }

    appendNumber(number) {
        if (this.currentOperand === 'Error') {
            this.clear();
        }
        if (number === '.' && this.currentOperand.includes('.')) return;
        if (this.currentOperand === '0' && number !== '.') {
            this.currentOperand = number;
        } else {
            this.currentOperand = this.currentOperand.toString() + number;
        }
    }

    chooseOperation(operation) {
        if (this.currentOperand === 'Error') return;
        if (this.currentOperand === '' && this.previousOperand === '') return;
        if (this.previousOperand !== '' && this.currentOperand !== '0') {
            this.compute();
        }
        this.operation = operation;
        this.previousOperand = this.currentOperand;
        this.currentOperand = '0';
    }

    percent() {
        if (this.currentOperand === 'Error') return;
        const current = parseFloat(this.currentOperand);
        if (isNaN(current)) return;
        this.currentOperand = (current / 100).toString();
    }

    compute() {
        let computation;
        const prev = parseFloat(this.previousOperand);
        const current = parseFloat(this.currentOperand);
        if (isNaN(prev) || isNaN(current)) return;

        switch (this.operation) {
            case '+':
                computation = prev + current;
                break;
            case '-':
            case '−':
                computation = prev - current;
                break;
            case '×':
                computation = prev * current;
                break;
            case '÷':
                if (current === 0) {
                    this.currentOperand = 'Error';
                    this.previousOperand = '';
                    this.operation = undefined;
                    this.updateDisplay();
                    return;
                }
                computation = prev / current;
                break;
            default:
                return;
        }

        // Handle floating point precision
        this.currentOperand = parseFloat(computation.toPrecision(12)).toString();
        this.operation = undefined;
        this.previousOperand = '';
    }

    updateDisplay() {
        this.currentOperandEl.innerText = this.currentOperand;
        if (this.operation != null) {
            this.previousOperandEl.innerText = `${this.previousOperand} ${this.operation}`;
        } else {
            this.previousOperandEl.innerText = '';
        }
    }
}

// Initialize Calculator
const previousOperandEl = document.getElementById('previous-operand');
const currentOperandEl = document.getElementById('current-operand');
const calculator = new Calculator(previousOperandEl, currentOperandEl);

// Button event listeners
document.querySelectorAll('.btn').forEach(button => {
    button.addEventListener('click', () => {
        const action = button.dataset.action;
        const value = button.dataset.value;

        switch (action) {
            case 'number':
                calculator.appendNumber(value);
                break;
            case 'decimal':
                calculator.appendNumber('.');
                break;
            case 'operator':
                calculator.chooseOperation(value);
                break;
            case 'equals':
                calculator.compute();
                break;
            case 'clear':
                calculator.clear();
                break;
            case 'delete':
                calculator.delete();
                break;
            case 'percent':
                calculator.percent();
                break;
        }

        calculator.updateDisplay();
    });
});

// Keyboard support
document.addEventListener('keydown', (e) => {
    if (e.key >= '0' && e.key <= '9') {
        calculator.appendNumber(e.key);
    } else if (e.key === '.') {
        calculator.appendNumber('.');
    } else if (e.key === '+') {
        calculator.chooseOperation('+');
    } else if (e.key === '-') {
        calculator.chooseOperation('−');
    } else if (e.key === '*') {
        calculator.chooseOperation('×');
    } else if (e.key === '/') {
        e.preventDefault();
        calculator.chooseOperation('÷');
    } else if (e.key === '%') {
        calculator.percent();
    } else if (e.key === 'Enter' || e.key === '=') {
        calculator.compute();
    } else if (e.key === 'Backspace') {
        calculator.delete();
    } else if (e.key === 'Escape') {
        calculator.clear();
    }

    calculator.updateDisplay();
});

// Theme toggle
const themeToggleBtn = document.getElementById('theme-toggle-btn');
const htmlEl = document.documentElement;

function updateThemeIcon() {
    const theme = htmlEl.getAttribute('data-theme');
    themeToggleBtn.textContent = theme === 'dark' ? '🌙' : '☀️';
}

themeToggleBtn.addEventListener('click', () => {
    const currentTheme = htmlEl.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    htmlEl.setAttribute('data-theme', newTheme);
    localStorage.setItem('calculator-theme', newTheme);
    updateThemeIcon();
});

// Load saved theme or use default (dark)
const savedTheme = localStorage.getItem('calculator-theme') || 'dark';
htmlEl.setAttribute('data-theme', savedTheme);
updateThemeIcon();

// Initialize display
calculator.updateDisplay();
