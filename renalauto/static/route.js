// «Путь машины» под сценой порта: машина, выбранная на стоянке (событие renal:car из port.js),
// проходит пять шагов — судном из Кореи или автовозом из Китая.
(() => {
  const box = document.querySelector('[data-route]');
  if (!box) return;
  const steps = [...box.querySelectorAll('[data-route-step]')];
  const fill = box.querySelector('[data-route-fill]');
  const veh = box.querySelector('[data-route-veh]');
  const carEl = box.querySelector('[data-route-car]');
  const cta = box.querySelector('[data-route-cta]');
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

  addEventListener('renal:car', e => {
    const {title, country, turnkey} = e.detail || {};
    if (!title) return;
    const cn = country === 'cn';
    box.classList.add('picked');
    box.classList.toggle('cn', cn);
    box.querySelectorAll('[data-kr]').forEach(el => { el.hidden = cn; });
    box.querySelectorAll('[data-cn]').forEach(el => { el.hidden = !cn; });
    carEl.textContent = `${title} — ${cn ? 'из Китая по суше' : 'из Кореи морем'}${turnkey ? `, от ${Math.round(turnkey).toLocaleString('ru-RU')} ₽ под ключ` : ''}`;
    cta.hidden = false;
    play();
  });
})();
