// Блок «Путь машины»: по мере прокрутки машинки едут по маршрутам, загораются этапы.
(() => {
  const box = document.querySelector('[data-journey]');
  if (!box) return;
  const steps = [...box.querySelectorAll('[data-j-step]')];
  const routes = ['kr', 'cn', 'ru'].map(id => {
    const path = box.querySelector(`[data-j-progress="${id}"]`);
    const len = path.getTotalLength();
    path.style.strokeDasharray = `${len}`;
    return {id, path, len, car: box.querySelector(`[data-j-car="${id}"]`)};
  });

  // 0…0.6 — Корея и Китай до Владивостока, 0.6…1 — по России до вашего города
  function render(p) {
    for (const r of routes) {
      const t = r.id === 'ru' ? Math.max(0, Math.min(1, (p - 0.6) / 0.4)) : Math.min(1, p / 0.6);
      r.path.style.strokeDashoffset = `${r.len * (1 - t)}`;
      const pt = r.path.getPointAtLength(r.len * t);
      r.car.setAttribute('transform', `translate(${pt.x.toFixed(1)} ${pt.y.toFixed(1)})`);
      r.car.classList.toggle('on', r.id === 'ru' ? p > 0.6 : p < 0.62);
    }
    // этапы в такт карте: выкуп → экспорт (в пути) → Владивосток (p = 0,6) → по России → ключи
    const active = [0, 0.12, 0.58, 0.68, 0.97].filter(t => p >= t).length - 1;
    steps.forEach((s, i) => { s.classList.toggle('done', i < active); s.classList.toggle('on', i === active); });
  }

  if (matchMedia('(prefers-reduced-motion: reduce)').matches) { render(1); return; }
  let ticking = false;
  function update() {
    ticking = false;
    const r = box.getBoundingClientRect(), vh = innerHeight;
    // путь проходится, пока верх блока поднимается от 85 % до 15 % высоты экрана
    const p = (vh * 0.85 - r.top) / (vh * 0.7);
    render(Math.max(0, Math.min(1, p)));
  }
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, {passive: true});
  addEventListener('resize', update);
  update();
})();
