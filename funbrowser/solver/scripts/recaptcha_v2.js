// reCAPTCHA v2 — checkbox + invisible.
//
// Widget: <div class="g-recaptcha" data-sitekey="..."> (with optional
// data-size="invisible", data-callback="myFn", data-s="...").
// Response: textarea#g-recaptcha-response. For pages with multiple
// widgets the textareas are numbered (g-recaptcha-response-0, -1, ...).
(() => {
  if (!window.__funbrowser) return;
  if (window.__funbrowser._recaptchaV2Installed) return;
  window.__funbrowser._recaptchaV2Installed = true;

  const seen = new WeakSet();

  function injectToken(token) {
    document
      .querySelectorAll(
        'textarea[id^="g-recaptcha-response"], textarea[name="g-recaptcha-response"]'
      )
      .forEach((ta) => {
        ta.value = token;
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        ta.dispatchEvent(new Event('change', { bubbles: true }));
      });
    if (window.grecaptcha) {
      try {
        window.grecaptcha.getResponse = function () { return token; };
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
    const dataS = el.dataset.s || el.getAttribute('data-s') || undefined;

    try {
      const token = await window.__funbrowser.solve({
        type: 'recaptcha2',
        sitekey,
        url: location.href,
        invisible,
        dataS,
      });
      injectToken(token);
      const cb = el.dataset.callback || el.getAttribute('data-callback');
      if (cb && typeof window[cb] === 'function') {
        try { window[cb](token); } catch (e) {}
      }
    } catch (e) {
      console.error('[funbrowser] recaptcha2 solve failed:', e);
    }
  }

  function scan(root) {
    (root || document)
      .querySelectorAll('.g-recaptcha[data-sitekey]')
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
        if (n.classList && n.classList.contains('g-recaptcha')) handle(n);
        else scan(n);
      });
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
