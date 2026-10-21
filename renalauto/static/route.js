// «Путь машины» под сценой порта: машина, выбранная на стоянке (событие renal:car из port.js),
// проходит пять шагов — судном из Кореи или автовозом из Китая.
(() => {
  const box = document.querySelector('[data-route]');
  if (!box) return;
  const steps = [...box.querySelectorAll('[data-route-step]')];
  const fill = box.querySelector('[data-route-fill]');
  const veh = box.querySelector('[data-route-veh]');
  const carEl = box.querySelector('[data-route-car]');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  let raf = 0;

  // t: 0…1 по линии от первого шага до последнего
  function show(t) {
    const active = Math.min(steps.length - 1, Math.round(t * (steps.length - 1)));
    steps.forEach((s, i) => { s.classList.toggle('done', i < active); s.classList.toggle('on', i === active); });
    fill.style.width = `${(t * 100).toFixed(1)}%`;
    veh.style.left = `${(t * 100).toFixed(1)}%`;
  }

  function play() {
    cancelAnimationFrame(raf);
    if (reduce.matches) { show(1); return; }
    const t0 = performance.now(), dur = 3200;
    const tick = now => {
      const k = Math.min(1, (now - t0) / dur);
      show(k < .5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
  }

  // сцена порта ведёт полосу сама, когда показывает доставку: at(t) — встать, run(a, b, ms) — проехать
  function run(a, b, ms) {
    cancelAnimationFrame(raf);
    if (reduce.matches) { show(b); return; }
    const t0 = performance.now();
    const tick = now => { const k = Math.min(1, (now - t0) / ms); show(a + (b - a) * k); if (k < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
  }
  window.RenalRoute = {at: t => { cancelAnimationFrame(raf); show(t); }, run};

  addEventListener('renal:car', e => {
    const {title, country, turnkey, manual} = e.detail || {};
    if (!title) return;
    const cn = country === 'cn';
    box.classList.add('picked');
    box.classList.toggle('cn', cn);
    box.querySelectorAll('[data-kr]').forEach(el => { el.hidden = cn; });
    box.querySelectorAll('[data-cn]').forEach(el => { el.hidden = !cn; });
    carEl.textContent = `${title} — ${cn ? 'из Китая по суше' : 'из Кореи морем'}${turnkey ? `, ≈ ${Math.round(turnkey).toLocaleString('ru-RU')} ₽ с растаможкой` : ''}`;
    if (!manual) play();
  });
})();

// «Сделка и оплата»: когда блок показался, судно уходит от площадки к Владивостоку, станции загораются по очереди
(() => {
  const map = document.querySelector('[data-deal-map]');
  if (!map) return;
  map.querySelectorAll('[data-deal-pin]').forEach((p, i) => p.style.setProperty('--i', i));
  if (!('IntersectionObserver' in window)) { map.classList.add('go'); return; }
  const io = new IntersectionObserver(es => {
    if (es.some(e => e.isIntersecting)) { map.classList.add('go'); io.disconnect(); }
  }, {threshold: 0.6});
  io.observe(map);
})();
