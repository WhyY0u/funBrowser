(() => {
  const fp = window.__funbrowser_fp;
  if (!fp || !fp.platform) return;
  const map = {
    'Windows': 'Win32',
    'macOS': 'MacIntel',
    'Linux': fp.architecture === 'arm' ? 'Linux armv8l' : 'Linux x86_64',
    'Android': 'Linux armv8l',
  };
  const platformValue = map[fp.platform] || fp.platform;
  const getter = window.__fb_m
    ? window.__fb_m(function () { return platformValue; }, 'get platform')
    : function () { return platformValue; };
  Object.defineProperty(navigator, 'platform', {
    get: getter,
    configurable: true,
  });
})();
