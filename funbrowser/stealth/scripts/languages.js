(() => {
  const fp = window.__funbrowser_fp;
  const langs = (fp && Array.isArray(fp.languages) && fp.languages.length > 0)
    ? fp.languages.slice()
    : ['en-US', 'en'];
  const getter = window.__fb_m
    ? window.__fb_m(function () { return langs.slice(); }, 'get languages')
    : function () { return langs.slice(); };
  Object.defineProperty(navigator, 'languages', {
    get: getter,
    configurable: true,
  });
})();
