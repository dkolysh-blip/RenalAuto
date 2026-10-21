// «Путь машины» под сценой порта: вода из терминала продолжается в полосе — судно уходит из Пусана во Владивосток,
// дальше автовоз везёт машину в ваш город; из Китая весь путь по суше. Прокрутка двигает транспорт,
// под полосой — карточка этапа с настоящим фото. Сцена порта управляет полосой через RenalRoute и событие renal:car.
(() => {
  const box = document.querySelector('[data-route]');
  const dataEl = document.getElementById('vy-data');
  if (!box || !dataEl) return;
  const DATA = JSON.parse(dataEl.textContent);
  const $ = s => box.querySelector(s), $$ = s => [...box.querySelectorAll(s)];
  const ship = $('[data-vy-ship]'), truck = $('[data-vy-truck]'), wake = $('[data-vy-wake]');
  const pins = $$('[data-vy-pin]'), steps = $$('[data-vy-step]');
  const card = {el: $('[data-vy-card]'), photo: $('[data-vy-photo]'), num: $('[data-vy-num]'),
    title: $('[data-vy-title]'), text: $('[data-vy-text]'), meta: $('[data-vy-meta]')};
  const carEl = $('[data-route-car]');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, k) => a + (b - a) * k;
  let mode = 'kr', stage = -1, t = 0, raf = 0, locked = false, lockY = 0;

  function fillSteps() {
    steps.forEach((b, i) => { b.querySelector('[data-vy-step-title]').textContent = DATA[mode][i].title; });
    pins.forEach((p, i) => { p.querySelector('[data-vy-pin-label]').textContent = DATA[mode][i].short; });
    $$('.vy-dist').forEach(d => { d.textContent = d.dataset[mode]; });
  }
  function showCard(i) {
    const s = DATA[mode][i];
    card.photo.src = `/static/media/route/${s.photo}.webp`;
    card.photo.alt = s.title;
    card.num.textContent = i + 1;
    card.title.textContent = s.title;
    card.text.textContent = s.text;
    card.meta.textContent = s.meta;
    card.el.classList.add('swap'); void card.el.offsetWidth; card.el.classList.remove('swap');  // заново проиграть появление
  }

  // t: 0…1 по всему пути; станции — на 4 %, 27 %, 50 %, 73 %, 96 % ширины полосы
  function show(next) {
    t = clamp(next);
    const land = mode === 'cn';
    if (land) {
      ship.style.opacity = 0; wake.style.opacity = 0;
      truck.style.opacity = 1; truck.style.left = `${lerp(4, 92, t)}%`;
    } else if (t <= 0.5) {  // судно идёт к причалу; --dock — сколько не доходит до берега (полкорпуса и причал)
      const k = t / 0.5, x = lerp(4, 50, k);
      ship.style.opacity = 1; ship.style.left = `calc(${x}% - ${k} * var(--dock))`;
      wake.style.opacity = t > 0.02 ? 1 : 0; wake.style.left = `${Math.max(0, x - 24)}%`; wake.style.width = `${Math.max(0, Math.min(x, 24) - 8)}%`;
      truck.style.opacity = 0; truck.style.left = '54%';
    } else {  // судно у причала, машину забирает автовоз
      ship.style.opacity = 1; ship.style.left = 'calc(50% - var(--dock))'; wake.style.opacity = 0;
      truck.style.opacity = 1; truck.style.left = `${lerp(56, 92, (t - 0.5) / 0.5)}%`;
    }
    const s = Math.round(t * 4);
    pins.forEach((p, i) => { p.classList.toggle('done', i < s); p.classList.toggle('on', i === s); });
    steps.forEach((b, i) => { b.parentElement.classList.toggle('done', i < s); b.parentElement.classList.toggle('on', i === s); });
    box.classList.toggle('arrived', t > 0.97);  // машина съехала с автовоза к дому
    if (s !== stage) { stage = s; showCard(s); }
  }

  function setMode(m) {
    mode = m === 'cn' ? 'cn' : 'kr';
    box.classList.toggle('land', mode === 'cn');
    $$('[data-vy-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.vyMode === mode)));
    fillSteps();
    stage = -1;
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

  // прокрутка: путь проходится, пока полоса поднимается от низа экрана к верхней трети
  function onScroll() {
    if (locked) { if (Math.abs(scrollY - lockY) < 160) return; locked = false; }
    const r = box.getBoundingClientRect(), vh = innerHeight;
    show((vh * 0.95 - r.top) / (vh * 0.95 - vh * 0.25));
  }
  let ticking = false;
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(() => { ticking = false; onScroll(); }); } }, {passive: true});
  addEventListener('resize', onScroll);

  $$('[data-vy-mode]').forEach(b => b.addEventListener('click', () => { setMode(b.dataset.vyMode); run(0, 1, 3600); }));
  steps.forEach((b, i) => b.addEventListener('click', () => run(t, i / 4, 700)));

  addEventListener('renal:car', e => {
    const {title, country, turnkey, manual, sprite} = e.detail || {};
    if (!title) return;
    box.classList.add('picked');
    if (sprite) $$('[data-vy-mine]').forEach(img => { img.src = sprite; });
    carEl.textContent = `${title} — ${country === 'cn' ? 'из Китая по суше' : 'из Кореи морем'}` +
      `${turnkey ? `, ≈ ${Math.round(turnkey).toLocaleString('ru-RU')} ₽ с растаможкой` : ''}`;
    setMode(country);
    if (!manual) run(0, 1, 4200);
  });

  setMode('kr');
  if (reduce.matches) show(0); else onScroll();
})();
