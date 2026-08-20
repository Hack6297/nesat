async function refreshStatus() {
  try {
    const response = await fetch('status.json', { cache: 'no-store' });
    if (!response.ok) return;
    const data = await response.json();

    const pagesEl = document.querySelector('[data-stat="pages"]');
    const termsEl = document.querySelector('[data-stat="terms"]');
    const crawlEl = document.querySelector('[data-stat="crawl"]');
    if (pagesEl) pagesEl.textContent = `${data.page_count} pages`;
    if (termsEl) termsEl.textContent = `${data.term_count} terms`;
    if (crawlEl) crawlEl.textContent = `latest ${data.latest_crawl}`;

    const liveStatus = document.getElementById('live-status');
    if (liveStatus) {
      if (data.index_running && data.index_message) {
        liveStatus.innerHTML = `<section class="window message-window"><div class="window-body"><p style="color:green; font-weight:bold; margin:0;">${escapeHtml(data.index_message)}</p></div></section>`;
      } else if (data.index_error) {
        liveStatus.innerHTML = `<section class="window message-window"><div class="window-body"><p style="color:red; font-weight:bold; margin:0;">${escapeHtml(data.index_error)}</p></div></section>`;
      } else if (!data.index_running) {
        const panel = liveStatus.querySelector('.message-window');
        if (panel && panel.innerHTML.includes('green')) {
          setTimeout(() => { liveStatus.innerHTML = ''; }, 5000);
        }
      }
    }
  } catch (error) {
    // silently fail
  }
}

async function refreshNews() {
  try {
    const response = await fetch('news-fragment', { cache: 'no-store' });
    if (!response.ok) return;
    const html = await response.text();
    const newsHost = document.getElementById('bbc-news-feed');
    if (newsHost) {
      newsHost.innerHTML = html;
    }
  } catch (error) {
    // silently fail
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function setupClearButtons() {
  const clearButtons = document.querySelectorAll('[data-clear-target]');
  clearButtons.forEach((button) => {
    button.addEventListener('click', (event) => {
      event.preventDefault();
      const targetId = button.getAttribute('data-clear-target');
      const target = targetId ? document.getElementById(targetId) : null;
      if (!target) return;
      target.value = '';
      target.focus();
    });
  });
}

function setupWindowToggles() {
  const toggleButtons = document.querySelectorAll('[data-window-toggle]');
  toggleButtons.forEach((button) => {
    button.addEventListener('click', (event) => {
      event.preventDefault();
      const hostWindow = button.closest('.window');
      if (!hostWindow) return;
      const isMinimized = hostWindow.classList.toggle('is-minimized');
      button.setAttribute('aria-label', isMinimized ? 'Restore' : 'Minimize');
      button.setAttribute('title', isMinimized ? 'Restore' : 'Minimize');
    });
  });
}

window.addEventListener('load', () => {
  refreshStatus();
  refreshNews();
  setupClearButtons();
  setupWindowToggles();
  window.setInterval(refreshStatus, 4000);
});
