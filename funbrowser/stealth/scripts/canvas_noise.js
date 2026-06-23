(() => {
  // Add 1-LSB noise to canvas readouts so fingerprint hashes vary per session.
  // Note: only breaks tracking by hash, doesn't fake a specific GPU's output —
  // that's M9 territory. Real GPU via --use-gl=angle gives realistic baseline.
  const clamp = (v) => (v < 0 ? 0 : v > 255 ? 255 : v);
  const noise = () => Math.floor(Math.random() * 3) - 1;

  const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
  CanvasRenderingContext2D.prototype.getImageData = function (...args) {
    const data = origGetImageData.apply(this, args);
    const a = data.data;
    for (let i = 0; i < a.length; i += 4) {
      a[i] = clamp(a[i] + noise());
      a[i + 1] = clamp(a[i + 1] + noise());
      a[i + 2] = clamp(a[i + 2] + noise());
    }
    return data;
  };

  const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function (...args) {
    const ctx = this.getContext && this.getContext('2d');
    if (ctx && this.width > 0 && this.height > 0) {
      try {
        const d = ctx.getImageData(0, 0, this.width, this.height);
        ctx.putImageData(d, 0, 0);
      } catch (_) {}
    }
    return origToDataURL.apply(this, args);
  };

  const origToBlob = HTMLCanvasElement.prototype.toBlob;
  HTMLCanvasElement.prototype.toBlob = function (cb, ...rest) {
    const ctx = this.getContext && this.getContext('2d');
    if (ctx && this.width > 0 && this.height > 0) {
      try {
        const d = ctx.getImageData(0, 0, this.width, this.height);
        ctx.putImageData(d, 0, 0);
      } catch (_) {}
    }
    return origToBlob.call(this, cb, ...rest);
  };
})();
