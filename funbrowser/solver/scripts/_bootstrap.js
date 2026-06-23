(() => {
  if (window.__funbrowser) return;
  const pending = new Map();
  let nextId = 0;

  window.__funbrowser = {
    solve(req) {
      return new Promise((resolve, reject) => {
        const id = ++nextId;
        pending.set(id, { resolve, reject });
        // The binding is a CDP-injected function that takes a single string.
        try {
          window.__funbrowser_solve(JSON.stringify({ id, ...req }));
        } catch (e) {
          pending.delete(id);
          reject(e);
        }
      });
    },
  };

  // Called by the host (Python side) via Runtime.evaluate.
  window.__funbrowser_resolve = (id, result) => {
    const p = pending.get(id);
    if (!p) return;
    pending.delete(id);
    if (result && result.ok) p.resolve(result.token);
    else p.reject(new Error((result && result.error) || 'funsolver: unknown error'));
  };
})();
