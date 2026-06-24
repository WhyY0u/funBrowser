// reCAPTCHA v3 — score-based, no visible widget.
//
// Pages call `grecaptcha.execute(sitekey, {action: 'login'})` to get a
// token. We hook execute() so it asks funsolver for a real token instead
// of running Google's verifier.
(() => {
  if (!window.__funbrowser) return;
  if (window.__funbrowser._recaptchaV3Installed) return;
  window.__funbrowser._recaptchaV3Installed = true;

  function install() {
    if (!window.grecaptcha || !window.grecaptcha.execute) return false;
    if (window.grecaptcha.execute.__fbHooked) return true;
    const orig = window.grecaptcha.execute;
    const hooked = async function (sitekey, options) {
      const action = (options && options.action) || 'verify';
      try {
        return await window.__funbrowser.solve({
          type: 'recaptcha3',
          sitekey,
          url: location.href,
          action,
          minScore: 0.7,
        });
      } catch (e) {
        console.error('[funbrowser] recaptcha3 solve failed:', e);
        return orig.call(this, sitekey, options);
      }
    };
    hooked.__fbHooked = true;
    window.grecaptcha.execute = hooked;
    return true;
  }

  if (install()) return;
  // grecaptcha may load after our script — poll for up to 30s and watch DOM.
  let attempts = 30;
  const interval = setInterval(() => {
    if (install() || --attempts <= 0) clearInterval(interval);
  }, 1000);
  const observer = new MutationObserver(() => {
    if (install()) observer.disconnect();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
