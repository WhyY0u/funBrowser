(() => {
  const fp = window.__funbrowser_fp;
  if (!fp || !fp.platform) return;
  const map = {
    'Windows': 'Win32',
    'macOS': 'MacIntel',
    'Linux': fp.architecture === 'arm' ? 'Linux armv8l' : 'Linux x86_64',
    'Android': 'Linux armv8l',
  };
  const platform = map[fp.platform] || fp.platform;
  Object.defineProperty(navigator, 'platform', {
    get: () => platform,
    configurable: true,
  });
})();
