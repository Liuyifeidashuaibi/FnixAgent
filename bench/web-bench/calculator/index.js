function calculateSin() {
  const display = document.getElementById('display');
  const value = parseFloat(display.textContent);
  if (isNaN(value)) {
    display.textContent = 'Error';
    return;
  }
  const result = Math.sin(value);
  display.textContent = result;
}

// Attach the function to the sin button
document.getElementById('sin-btn').addEventListener('click', calculateSin);