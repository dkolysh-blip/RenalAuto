// «Как привезём» под сценой порта: пять этапов в ряд, переключатель Корея / Китай.
// Сцена порта подсвечивает этап через RenalRoute (t: 0…1 по пути) и сообщает выбранную машину событием renal:car.
(() => {
  const box = document.querySelector('[data-route]');
  if (!box) return;
  const carEl = box.querySelector('[data-route-car]');
  let timer = 0;
  function setMode(m) {
    box.dataset.mode = m === 'cn' ? 'cn' : 'kr';
    box.querySelectorAll('[data-vy-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.vyMode === box.dataset.mode)));
  }
  function mark(i) {
    box.querySelectorAll('[data-r2-step]').forEach(li => {
      li.classList.toggle('done', +li.dataset.r2Step < i);
      li.classList.toggle('on', +li.dataset.r2Step === i);
    });
  }
  const at = v => Math.max(0, Math.min(4, Math.round(v * 4)));
  window.RenalRoute = {
    at: v => { clearInterval(timer); mark(at(v)); },
    run: (a, b = 1, ms = 6000) => {
      clearInterval(timer);
      let i = at(a); const end = at(b); mark(i);
      timer = setInterval(() => { i += 1; mark(i); if (i >= end) clearInterval(timer); }, ms / Math.max(1, end - at(a)));
    },
  };
  box.querySelectorAll('[data-vy-mode]').forEach(b => b.addEventListener('click', () => setMode(b.dataset.vyMode)));
  addEventListener('renal:car', e => {
    const {title, country, turnkey} = e.detail || {};
    if (!title) return;
    carEl.innerHTML = `<b></b> — ${country === 'cn' ? 'из Китая по суше' : 'из Кореи морем'}` +
      `${turnkey ? `, ≈ ${Math.round(turnkey).toLocaleString('ru-RU')} ₽ с растаможкой` : ''}`;
    carEl.querySelector('b').textContent = title;
    setMode(country);
  });
  setMode('kr');
})();
