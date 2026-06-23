(() => {
  // Headless Chrome exposes navigator.plugins as an empty PluginArray.
  // Real Chrome (since 109) returns a small fixed set of PDF-related plugins.
  // Re-create a PluginArray-shaped object that matches.
  const mkPlugin = (name, filename, description) => {
    const p = Object.create(Plugin.prototype);
    Object.defineProperties(p, {
      name: { value: name, enumerable: true },
      filename: { value: filename, enumerable: true },
      description: { value: description, enumerable: true },
      length: { value: 1, enumerable: true },
    });
    const mime = Object.create(MimeType.prototype);
    Object.defineProperties(mime, {
      type: { value: 'application/pdf', enumerable: true },
      suffixes: { value: 'pdf', enumerable: true },
      description: { value: 'Portable Document Format', enumerable: true },
      enabledPlugin: { value: p, enumerable: true },
    });
    p[0] = mime;
    return p;
  };
  const plugins = [
    mkPlugin('PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
    mkPlugin('Chrome PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
    mkPlugin('Chromium PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
    mkPlugin('Microsoft Edge PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
    mkPlugin('WebKit built-in PDF', 'internal-pdf-viewer', 'Portable Document Format'),
  ];
  const arr = Object.create(PluginArray.prototype);
  plugins.forEach((p, i) => { arr[i] = p; arr[p.name] = p; });
  Object.defineProperty(arr, 'length', { value: plugins.length });
  arr.item = (i) => plugins[i] || null;
  arr.namedItem = (n) => plugins.find((p) => p.name === n) || null;
  arr.refresh = () => undefined;
  Object.defineProperty(navigator, 'plugins', { get: () => arr, configurable: true });
})();
