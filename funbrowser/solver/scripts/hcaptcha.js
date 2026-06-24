// hCaptcha — `.h-captcha[data-sitekey]` widgets.
//
// Response goes into `textarea[name="h-captcha-response"]` (some pages
// also expect g-recaptcha-response for back-compat). Optional
// data-callback on the div.
(() => {
  if (!window.__funbrowser) return;
  if (window.__funbrowser._hcaptchaInstalled) return;
  window.__funbrowser._hcaptchaInstalled = true;

  const seen = new WeakSet();

  function injectToken(token) {
    document
      .querySelectorAll(
        'textarea[name="h-captcha-response"], textarea[name="g-recaptcha-response"]'
      )
      .forEach((ta) => {
        ta.value = token;
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        ta.dispatchEvent(new Event('change', { bubbles: true }));
      });
    if (window.hcaptcha) {
      try {
        window.hcaptcha.getResponse = function () { return token; };
      } catch (e) {}
    }
  }

  async function handle(el) {
    if (seen.has(el)) return;
    seen.add(el);
    const sitekey = el.dataset.sitekey || el.getAttribute('data-sitekey');
    if (!sitekey) return;

    const invisible =
      (el.dataset.size || el.getAttribute('data-size')) === 'invisible';

    try {
      const token = await window.__funbrowser.solve({
        type: 'hcaptcha',
        sitekey,
        url: location.href,
        invisible,
      });
      injectToken(token);
      const cb = el.dataset.callback || el.getAttribute('data-callback');
      if (cb && typeof window[cb] === 'function') {
        try { window[cb](token); } catch (e) {}
      }
    } catch (e) {
      console.error('[funbrowser] hcaptcha solve failed:', e);
    }
  }

  function scan(root) {
    (root || document)
      .querySelectorAll('.h-captcha[data-sitekey]')
      .forEach(handle);
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
        if (n.classList && n.classList.contains('h-captcha')) handle(n);
        else scan(n);
      });
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
