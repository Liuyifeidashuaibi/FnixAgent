let timerDisplay = document.getElementById('timer');
let startBtn = document.getElementById('startBtn');
let pauseBtn = document.getElementById('pauseBtn');
let resetBtn = document.getElementById('resetBtn');
let sessionDisplay = document.getElementById('session');

let timeLeft = 25 * 60; // 25 minutes in seconds
let interval;
let isRunning = false;
let session = 1;
let isBreak = false;

function updateTimer() {
    let minutes = Math.floor(timeLeft / 60);
    let seconds = timeLeft % 60;
    timerDisplay.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

function startTimer() {
    if (!isRunning) {
        isRunning = true;
        interval = setInterval(() => {
            if (timeLeft > 0) {
                timeLeft--;
                updateTimer();
            } else {
                clearInterval(interval);
                playBeep();
                if (isBreak) {
                    session++;
                    isBreak = false;
                    timeLeft = 25 * 60;
                } else {
                    isBreak = true;
                    timeLeft = 5 * 60;
                }
                sessionDisplay.textContent = isBreak ? `Break ${session}` : `Work ${session}`;
                updateTimer();
            }
        }, 1000);
    }
}

function pauseTimer() {
    if (isRunning) {
        clearInterval(interval);
        isRunning = false;
    }
}

function resetTimer() {
    pauseTimer();
    timeLeft = 25 * 60;
    isBreak = false;
    session = 1;
    updateTimer();
    sessionDisplay.textContent = `Work ${session}`;
}

function playBeep() {
    let audio = new Audio('beep.mp3');
    audio.play();
}

startBtn.addEventListener('click', startTimer);
pauseBtn.addEventListener('click', pauseTimer);
resetBtn.addEventListener('click', resetTimer);

// Initial timer update
updateTimer();