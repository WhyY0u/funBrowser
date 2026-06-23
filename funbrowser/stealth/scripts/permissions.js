(() => {
  if (!navigator.permissions || !navigator.permissions.query) return;
  const orig = navigator.permissions.query.bind(navigator.permissions);
  navigator.permissions.query = (params) => {
    if (params && params.name === 'notifications') {
      // Headless: Notification.permission says 'default' but permissions.query
      // disagrees. Real Chrome: both say the same thing.
      return Promise.resolve({
        state: Notification.permission === 'default' ? 'prompt' : Notification.permission,
        onchange: null,
      });
    }
    return orig(params);
  };
})();
