(() => {
  const fp = window.__funbrowser_fp;
  if (!fp || !fp.screen) return;
  const s = fp.screen;
  const set = (key, value) => {
    if (value === undefined || value === null) return;
    const getter = window.__fb_m
      ? window.__fb_m(function () { return value; }, 'get ' + key)
      : function () { return value; };
    Object.defineProperty(screen, key, { get: getter, configurable: true });
  };
  set('width', s.width);
  set('height', s.height);
  set('availWidth', s.availWidth);
  set('availHeight', s.availHeight);
  set('colorDepth', s.colorDepth);
  set('pixelDepth', s.colorDepth);
})();
