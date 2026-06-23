(() => {
  const fp = window.__funbrowser_fp;
  if (!fp) return;
  const def = (obj, key, value) => {
    if (value === undefined || value === null) return;
    const getter = window.__fb_m
      ? window.__fb_m(function () { return value; }, 'get ' + key)
      : function () { return value; };
    Object.defineProperty(obj, key, { get: getter, configurable: true });
  };
  def(navigator, 'hardwareConcurrency', fp.hardwareConcurrency);
  def(navigator, 'deviceMemory', fp.deviceMemory);
  def(navigator, 'maxTouchPoints', fp.maxTouchPoints);
  def(window, 'devicePixelRatio', fp.devicePixelRatio);
})();
