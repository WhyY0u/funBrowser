(() => {
  if (navigator.webdriver === undefined) return;
  try {
    delete Object.getPrototypeOf(navigator).webdriver;
  } catch (_) {}
  Object.defineProperty(Navigator.prototype, 'webdriver', {
    get: () => undefined,
    configurable: true,
    enumerable: true,
  });
})();
