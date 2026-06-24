// FunCaptcha / Arkose Labs.
//
// Common attach points:
//   <div class="funcaptcha" data-pkey="..."></div>
//   <input data-pkey="...">  (some sites mark it on an input)
//   iframe[src*="funcaptcha"]  → look up parent for data-pkey
//
// Response goes into one of: input[name="fc-token"],
// input[name="arkose-token"], input[name="verification-token"].
// Optional data-callback name on the host element.
(() => {
  if (!window.__funbrowser) return;
  if (window.__funbrowser._funcaptchaInstalled) return;
  window.__funbrowser._funcaptchaInstalled = true;

  const seen = new WeakSet();

  function injectToken(token) {
    document
      .querySelectorAll(
        'input[name="fc-token"], input[name="arkose-token"], input[name="verification-token"]'
      )
      .forEach((inp) => {
        inp.value = token;
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        inp.dispatchEvent(new Event('change', { bubbles: true }));
      });
  }

  async function handle(el) {
    if (seen.has(el)) return;
    seen.add(el);
    const pkey = el.dataset.pkey || el.getAttribute('data-pkey');
    if (!pkey) return;

    const surl =
      el.dataset.surl || el.getAttribute('data-surl') || undefined;

    try {
      const token = await window.__funbrowser.solve({
        type: 'funcaptcha',
        sitekey: pkey,
        url: location.href,
        surl,
      });
      injectToken(token);
      const cb = el.dataset.callback || el.getAttribute('data-callback');
      if (cb && typeof window[cb] === 'function') {
        try { window[cb](token); } catch (e) {}
      }
    } catch (e) {
      console.error('[funbrowser] funcaptcha solve failed:', e);
    }
  }

  function scan(root) {
    (root || document).querySelectorAll('[data-pkey]').forEach(handle);
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
        if (n.dataset && n.dataset.pkey) handle(n);
        else scan(n);
      });
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
