(() => {
  if (!window.__funbrowser) return;
  if (window.__funbrowser._turnstileInstalled) return;
  window.__funbrowser._turnstileInstalled = true;

  const seen = new WeakSet();

  async function handle(el) {
    if (seen.has(el)) return;
    seen.add(el);

    const sitekey = el.dataset.sitekey || el.getAttribute('data-sitekey');
    if (!sitekey) return;

    try {
      const token = await window.__funbrowser.solve({
        type: 'turnstile',
        sitekey,
        url: location.href,
        action: el.dataset.action || el.getAttribute('data-action') || undefined,
        cdata: el.dataset.cdata || el.getAttribute('data-cdata') || undefined,
      });

      // Drop the token into the textarea Turnstile creates.
      const ta = document.querySelector('[name="cf-turnstile-response"]');
      if (ta) {
        ta.value = token;
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        ta.dispatchEvent(new Event('change', { bubbles: true }));
      }

      // Trigger the site's success callback (string or function).
      const cb = el.dataset.callback || el.getAttribute('data-callback');
      if (cb && typeof window[cb] === 'function') {
        try { window[cb](token); } catch (e) { console.error('[funbrowser] callback threw:', e); }
      }
    } catch (e) {
      console.error('[funbrowser] turnstile solve failed:', e);
    }
  }

  function scan(root) {
    (root || document).querySelectorAll('.cf-turnstile').forEach(handle);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => scan());
  } else {
    scan();
  }
  new MutationObserver((muts) => {
    for (const m of muts) {
      m.addedNodes.forEach((n) => {
        if (n.nodeType !== 1) return;
        if (n.classList && n.classList.contains('cf-turnstile')) handle(n);
        else scan(n);
      });
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
