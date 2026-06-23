(() => {
  if (navigator.webdriver === undefined) return;
  try {
    delete Object.getPrototypeOf(navigator).webdriver;
  } catch (_) {}
  const getter = window.__fb_m
    ? window.__fb_m(function () { return undefined; }, 'get webdriver')
    : function () { return undefined; };
  Object.defineProperty(Navigator.prototype, 'webdriver', {
    get: getter,
    configurable: true,
    enumerable: true,
  });
})();
