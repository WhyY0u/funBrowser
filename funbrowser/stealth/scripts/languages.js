(() => {
  const fp = window.__funbrowser_fp;
  const langs = (fp && Array.isArray(fp.languages) && fp.languages.length > 0)
    ? fp.languages.slice()
    : ['en-US', 'en'];
  Object.defineProperty(navigator, 'languages', {
    get: () => langs.slice(),
    configurable: true,
  });
})();
