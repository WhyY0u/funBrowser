// GeeTest v3 + v4.
//
// Pages typically fetch /geetest/register first to get {gt, challenge}, then
// call window.initGeetest({gt, challenge, ...}, onSuccessCallback) for v3 or
// initGeetest4({captchaId, ...}, cb) for v4. We hook both so the params get
// forwarded to funsolver and the page's success callback fires with a real
// validated payload.
(() => {
  if (!window.__funbrowser) return;
  if (window.__funbrowser._geetestInstalled) return;
  window.__funbrowser._geetestInstalled = true;

  function fillFields(payload) {
    // v3 payload fields
    if (payload.geetest_challenge !== undefined) {
      document
        .querySelectorAll('[name="geetest_challenge"]')
        .forEach((i) => { i.value = payload.geetest_challenge; });
    }
    if (payload.geetest_validate !== undefined) {
      document
        .querySelectorAll('[name="geetest_validate"]')
        .forEach((i) => { i.value = payload.geetest_validate; });
    }
    if (payload.geetest_seccode !== undefined) {
      document
        .querySelectorAll('[name="geetest_seccode"]')
        .forEach((i) => { i.value = payload.geetest_seccode; });
    }
  }

  function hookInit(name, version) {
    const orig = window[name];
    if (typeof orig === 'function' && orig.__fbHooked) return;

    const hooked = function (opts, callback) {
      const gt = (opts && (opts.gt || opts.captchaId)) || '';
      const challenge = (opts && opts.challenge) || '';
      if (!gt) {
        return orig ? orig.call(this, opts, callback) : undefined;
      }
      window.__funbrowser
        .solve({
          type: 'geetest',
          gt,
          challenge,
          url: location.href,
          version,
          apiServer: opts && opts.api_server,
        })
        .then((tokenRaw) => {
          let payload;
          try { payload = JSON.parse(tokenRaw); } catch (e) { payload = { token: tokenRaw }; }
          fillFields(payload);
          if (typeof callback === 'function') {
            try { callback(payload); } catch (e) {}
          }
        })
        .catch((e) => console.error('[funbrowser] geetest solve failed:', e));
    };
    hooked.__fbHooked = true;
    window[name] = hooked;
  }

  hookInit('initGeetest', 3);
  hookInit('initGeetest4', 4);

  // Re-hook periodically in case the GeeTest loader replaces window.initGeetest
  // after our patch (it often does once the loader script lands).
  let attempts = 30;
  const interval = setInterval(() => {
    hookInit('initGeetest', 3);
    hookInit('initGeetest4', 4);
    if (--attempts <= 0) clearInterval(interval);
  }, 1000);
})();
