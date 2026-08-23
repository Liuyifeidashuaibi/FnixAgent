document.addEventListener('DOMContentLoaded', function () {
  var isInFrame = window.self !== window.top;

  var btn = document.createElement('button');
  btn.className = 'open';
  btn.textContent = 'Open in new window';
  btn.style.display = isInFrame ? '' : 'none';
  document.body.appendChild(btn);

  btn.addEventListener('click', function () {
    window.open(window.location.href, '_blank');
  });

  if (!isInFrame) {
    btn.style.display = 'none';
  }
});
