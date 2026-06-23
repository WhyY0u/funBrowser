// Native-toString camouflage. Without this, our patched getters get caught by:
//   Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver').get.toString()
// returning something like '() => undefined' instead of 'function get webdriver() { [native code] }'.
//
// We install a Function.prototype.toString that, for any function the rest of the
// stealth pipeline registers via window.__fb_m(fn), returns the native-looking
// '[native code]' string. The new toString itself is registered too so it doesn't
// expose itself when stringified.
(() => {
  const origToString = Function.prototype.toString;
  const fakeNative = new WeakSet();

  const newToString = function () {
    if (fakeNative.has(this)) {
      return 'function ' + (this.name || '') + '() { [native code] }';
    }
    return origToString.call(this);
  };
  fakeNative.add(newToString);
  Function.prototype.toString = newToString;

  Object.defineProperty(window, '__fb_m', {
    value: (fn, name) => {
      if (name) Object.defineProperty(fn, 'name', { value: name, configurable: true });
      fakeNative.add(fn);
      return fn;
    },
    enumerable: false,
    configurable: true,
    writable: false,
  });
})();
