// Remove the registration helper exposed by _camouflage.js so downstream page
// scripts can't discover it. The functions it registered survive (they live in
// the closure's WeakSet); only the entry-point disappears.
(() => {
  try {
    delete window.__fb_m;
  } catch (e) {}
})();
