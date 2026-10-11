(() => {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let paused = reducedMotion.matches;
  const motion = document.querySelector('.motion-control');
  const video = document.querySelector('#browser-video');
  const panel = document.querySelector('#browser-evidence');
  let videoVisible = false;

  function syncMotion() {
    document.documentElement.classList.toggle('motion-paused', paused);
    if (motion) {
      motion.setAttribute('aria-pressed', String(paused));
      motion.textContent = paused ? motion.dataset.resume : motion.dataset.pause;
    }
    if (!video) return;
    if (paused || panel?.hidden || !videoVisible || document.hidden) video.pause();
    else video.play().catch(() => {});
  }
  if (motion) {
    motion.hidden = false;
    motion.addEventListener('click', () => { paused = !paused; syncMotion(); });
  }
  reducedMotion.addEventListener('change', event => { paused = event.matches; syncMotion(); });
  document.addEventListener('visibilitychange', syncMotion);
  if (video && 'IntersectionObserver' in window) {
    new IntersectionObserver(entries => {
      videoVisible = entries[0].isIntersecting;
      syncMotion();
    }, { threshold: 0.25 }).observe(video);
  }
  syncMotion();

  const tablist = document.querySelector('.case-tabs');
  const tabs = [...(tablist?.querySelectorAll('[role="tab"]') || [])];
  function selectTab(tab, focus = false) {
    tabs.forEach(item => {
      const active = item === tab;
      item.setAttribute('aria-selected', String(active));
      item.tabIndex = active ? 0 : -1;
      const target = document.getElementById(item.getAttribute('aria-controls'));
      if (target) target.hidden = !active;
    });
    if (focus) tab.focus();
    syncMotion();
  }
  if (tablist) tablist.hidden = false;
  tabs.forEach(tab => tab.addEventListener('click', () => selectTab(tab)));
  tablist?.addEventListener('keydown', event => {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const current = tabs.indexOf(document.activeElement);
    let next = current;
    if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else next = (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    selectTab(tabs[next], true);
  });

  document.querySelectorAll('[data-copy]').forEach(button => {
    if (!navigator.clipboard?.writeText) return;
    const label = button.textContent;
    button.hidden = false;
    button.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
        button.textContent = button.dataset.copied;
        button.setAttribute('aria-live', 'polite');
        setTimeout(() => { button.textContent = label; }, 2000);
      } catch {
        button.textContent = label;
      }
    });
  });
})();
