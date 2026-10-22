// «Путь машины» под сценой порта — как отслеживание посылки: линия из пяти этапов, по ней едет судно (Корея)
// или автовоз (Китай). Под линией у каждого этапа — что делаем, что вы получаете и что с деньгами.
// Прокрутка проводит по этапам; сцена порта управляет блоком через RenalRoute и событие renal:car.
(() => {
  const box = document.querySelector('[data-route]');
  const dataEl = document.getElementById('vy-data');
  if (!box || !dataEl) return;
  const DATA = JSON.parse(dataEl.textContent);
  const $ = s => box.querySelector(s), $$ = s => [...box.querySelectorAll(s)];
  const pins = $$('[data-vy-pin]'), steps = $$('[data-tk-step]');
  const fill = $('[data-tk-fill]'), veh = $('[data-tk-veh]'), sea = $('[data-tk-sea]'), geo = $('[data-tk-geo]');
  const carEl = $('[data-route-car]'), titleEl = $('[data-tk-title]');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
  let mode = 'kr', stage = -1, t = 0, raf = 0, locked = false, lockY = 0;

  function fill_() {
    const d = DATA[mode];
    titleEl.textContent = d.title;
    geo.innerHTML = d.geo.map(([text, left, width, cls]) =>
      `<span class="${cls}" style="left:${left}%;width:${width}%">${text}</span>`).join('');
    sea.style.left = `${d.sea[0]}%`; sea.style.width = `${d.sea[1]}%`;
    steps.forEach((li, i) => {
      const s = d.steps[i];
      li.querySelector('[data-tk-t]').textContent = s.title;
      li.querySelector('[data-tk-pl]').textContent = s.place;
      li.querySelector('[data-tk-do]').textContent = s.do;
      li.querySelector('[data-tk-get]').textContent = s.get;
      li.querySelector('[data-tk-money]').textContent = s.money;
      const img = li.querySelector('[data-tk-photo]');
      img.src = `/static/media/route/${s.photo}.webp`; img.alt = s.title;
    });
  }

  // t: 0…1 по всему пути; этапы — на 10 %, 30 %, 50 %, 70 %, 90 % ширины линии
  function show(next) {
    t = clamp(next);
    const x = 10 + t * 80;
    fill.style.width = `${x - 10}%`;
    veh.style.left = `${x}%`;
    // из Кореи до Владивостока — судно, дальше и из Китая — автовоз
    veh.classList.toggle('ship', mode === 'kr' && t < 0.5);
    const s = Math.round(t * 4);
    pins.forEach((p, i) => { p.classList.toggle('done', i < s); p.classList.toggle('on', i === s); });
    steps.forEach((li, i) => { li.classList.toggle('done', i < s); li.classList.toggle('on', i === s); });
    stage = s;
  }

  function setMode(m) {
    mode = m === 'cn' ? 'cn' : 'kr';
    box.classList.toggle('land', mode === 'cn');
    $$('[data-vy-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.vyMode === mode)));
    fill_();
    show(t);
  }

  function run(a, b, ms, then) {
    cancelAnimationFrame(raf);
    locked = true; lockY = scrollY;
    if (reduce.matches) { show(b); then && then(); return; }
    const t0 = performance.now();
    const tick = now => {
      const k = Math.min(1, (now - t0) / ms), e = k < .5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
      show(a + (b - a) * e);
      if (k < 1) raf = requestAnimationFrame(tick); else then && then();
    };
    raf = requestAnimationFrame(tick);
  }
  window.RenalRoute = {at: v => { cancelAnimationFrame(raf); locked = true; lockY = scrollY; show(v); }, run: (a, b, ms) => run(a, b, ms)};

  // прокрутка: путь проходится, пока блок поднимается от низа экрана к верхней трети
  function onScroll() {
    if (locked) { if (Math.abs(scrollY - lockY) < 160) return; locked = false; }
    const r = box.getBoundingClientRect(), vh = innerHeight;
    show((vh * 0.9 - r.top) / (vh * 0.9 - vh * 0.15));
  }
  let ticking = false;
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(() => { ticking = false; onScroll(); }); } }, {passive: true});
  addEventListener('resize', onScroll);

  $$('[data-vy-mode]').forEach(b => b.addEventListener('click', () => { setMode(b.dataset.vyMode); run(0, 1, 3600); }));
  $$('[data-vy-step]').forEach(b => b.addEventListener('click', () => run(t, +b.dataset.vyStep / 4, 600)));

  addEventListener('renal:car', e => {
    const {title, country, turnkey, manual} = e.detail || {};
    if (!title) return;
    box.classList.add('picked');
    carEl.innerHTML = `<b></b> — ${country === 'cn' ? 'из Китая по суше' : 'из Кореи морем'}` +
      `${turnkey ? `, ≈ ${Math.round(turnkey).toLocaleString('ru-RU')} ₽ с растаможкой` : ''}`;
    carEl.querySelector('b').textContent = title;
    setMode(country);
    if (!manual) run(0, 1, 4200);
  });

  setMode('kr');
  if (reduce.matches) show(0); else onScroll();
})();
