// Lightweight helper to avoid progress flicker and wrap fetches
(function () {
  function startProgressWithDelay(delay = 120) {
    let timer = setTimeout(() => {
      if (window.NProgress) {
        NProgress.start();
      }
    }, delay);
    return function stop() {
      clearTimeout(timer);
      if (window.NProgress) {
        NProgress.done();
      }
    };
  }

  function fetchWithProgress(input, init, delay = 120) {
    const stop = startProgressWithDelay(delay);
    return fetch(input, init).finally(() => stop());
  }

  // Expose globally
  window.startProgressWithDelay = startProgressWithDelay;
  window.fetchWithProgress = fetchWithProgress;
})();
