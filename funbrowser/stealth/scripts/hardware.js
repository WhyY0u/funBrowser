(() => {
  const fp = window.__funbrowser_fp;
  if (!fp) return;
  const def = (obj, key, value) => {
    if (value === undefined || value === null) return;
    Object.defineProperty(obj, key, { get: () => value, configurable: true });
  };
  def(navigator, 'hardwareConcurrency', fp.hardwareConcurrency);
  def(navigator, 'deviceMemory', fp.deviceMemory);
  def(navigator, 'maxTouchPoints', fp.maxTouchPoints);
  def(window, 'devicePixelRatio', fp.devicePixelRatio);
})();
