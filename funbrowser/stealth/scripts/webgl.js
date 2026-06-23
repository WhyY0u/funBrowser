(() => {
  const fp = window.__funbrowser_fp;
  if (!fp || !fp.webgl) return;
  const vendor = fp.webgl.vendor;
  const renderer = fp.webgl.renderer;
  if ((vendor === undefined || vendor === null) && (renderer === undefined || renderer === null)) return;

  // Note: hooking getParameter changes the strings WebGL reports, but the
  // rendered pixel output still comes from the real GPU underneath. Top
  // antibots compare rendered output against claimed GPU and will flag the
  // mismatch. Full shader-level spoofing is M9 territory.
  const hook = (proto) => {
    if (!proto || !proto.getParameter) return;
    const orig = proto.getParameter;
    proto.getParameter = function (param) {
      // UNMASKED_VENDOR_WEBGL = 37445, VENDOR = 7936
      if (vendor && (param === 37445 || param === 7936)) return vendor;
      // UNMASKED_RENDERER_WEBGL = 37446, RENDERER = 7937
      if (renderer && (param === 37446 || param === 7937)) return renderer;
      return orig.call(this, param);
    };
  };
  hook(WebGLRenderingContext.prototype);
  if (typeof WebGL2RenderingContext !== 'undefined') {
    hook(WebGL2RenderingContext.prototype);
  }
})();
