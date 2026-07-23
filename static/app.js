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

function setupLuckyButton() {
  const luckyBtn = document.getElementById('btn-lucky');
  const searchInput = document.getElementById('search-input');
  if (!luckyBtn || !searchInput) return;

  luckyBtn.addEventListener('click', (e) => {
    e.preventDefault();
    const query = searchInput.value.trim();
    if (query) {
      window.location.href = `search?q=${encodeURIComponent(query)}`;
    }
  });
}

window.addEventListener('load', () => {
  refreshStatus();
  refreshNews();
  setupLuckyButton();
  window.setInterval(refreshStatus, 4000);
});
