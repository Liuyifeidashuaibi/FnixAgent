document.addEventListener('DOMContentLoaded', function () {
  document.addEventListener('click', function (e) {
    var openBtn = e.target.closest('.open');
    if (!openBtn) return;

    // Create the doc page overlay
    var overlay = document.createElement('div');
    overlay.className = 'doc-page';
    overlay.style.cssText =
      'position:fixed;top:0;left:0;width:100%;height:100%;background:#fff;z-index:9999;overflow:auto;';

    // Create the close button
    var closeBtn = document.createElement('button');
    closeBtn.className = 'close';
    closeBtn.textContent = 'Close';
    closeBtn.style.cssText =
      'position:absolute;top:10px;right:10px;padding:6px 16px;cursor:pointer;';

    closeBtn.addEventListener('click', function () {
      overlay.remove();
    });

    overlay.appendChild(closeBtn);
    document.body.appendChild(overlay);
  });
});
