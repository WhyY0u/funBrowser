(() => {
  const fp = window.__funbrowser_fp;
  if (!fp || !fp.screen) return;
  const s = fp.screen;
  const set = (key, value) => {
    if (value === undefined || value === null) return;
    Object.defineProperty(screen, key, { get: () => value, configurable: true });
  };
  set('width', s.width);
  set('height', s.height);
  set('availWidth', s.availWidth);
  set('availHeight', s.availHeight);
  set('colorDepth', s.colorDepth);
  set('pixelDepth', s.colorDepth);
})();
