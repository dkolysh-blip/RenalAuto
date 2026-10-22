// «Путь машины» под сценой порта — как сторис: пять этапов, у каждого фото, что делаем, что вы получаете и что с деньгами.
// Когда блок на экране, этапы листаются сами (полоски сверху заполняются); нажатие, свайп или стрелки — вручную.
// Сцена порта управляет блоком через RenalRoute (t: 0…1 по пути) и событие renal:car.
(() => {
  const box = document.querySelector('[data-route]');
  const dataEl = document.getElementById('vy-data');
  if (!box || !dataEl) return;
  const DATA = JSON.parse(dataEl.textContent);
  const $ = s => box.querySelector(s), $$ = s => [...box.querySelectorAll(s)];
  const bars = $$('.tk-bars [data-vy-step]'), rows = $$('[data-tk-step]'), stageEl = $('[data-tk-stage]');
  const photo = $('[data-tk-photo]'), carEl = $('[data-route-car]');
  const f = {n: $('[data-tk-n]'), t: $('[data-tk-t]'), pl: $('[data-tk-pl]'), do: $('[data-tk-do]'), get: $('[data-tk-get]'), money: $('[data-tk-money]')};
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const STEP_MS = 5200;
  let mode = 'kr', stage = 0, raf = 0, t0 = 0, playing = false, visible = false, touched = false;

  function render() {
    const d = DATA[mode], s = d.steps[stage];
    $('[data-tk-title]').textContent = d.title;
    rows.forEach((r, i) => { r.querySelector('[data-tk-li]').textContent = d.steps[i].title; });
    f.n.textContent = String(stage + 1).padStart(2, '0');
    f.t.textContent = s.title; f.pl.textContent = s.place;
    f.do.textContent = s.do; f.get.textContent = s.get; f.money.textContent = s.money;
    photo.src = `/static/media/route/${s.photo}.webp`; photo.alt = s.title;
    bars.forEach((b, i) => { b.classList.toggle('done', i < stage); b.classList.toggle('on', i === stage); b.setAttribute('aria-selected', String(i === stage)); b.style.setProperty('--p', i < stage ? 1 : 0); });
    rows.forEach((r, i) => { r.classList.toggle('done', i < stage); r.classList.toggle('on', i === stage); });
    stageEl.classList.remove('swap'); void stageEl.offsetWidth; stageEl.classList.add('swap');  // заново проиграть появление
  }
  function go(i) { stage = (i + 5) % 5; t0 = performance.now(); render(); }

  // автопрокрутка: полоска текущего этапа заполняется, потом — следующий этап; после последнего — заново
  function tick(now) {
    if (!playing) return;
    const k = Math.min(1, (now - t0) / STEP_MS);
    bars[stage].style.setProperty('--p', k);
    if (k >= 1) go(stage + 1);
    raf = requestAnimationFrame(tick);
  }
  function play() { if (playing || reduce.matches || touched) return; playing = true; t0 = performance.now(); raf = requestAnimationFrame(tick); }
  function pause() { playing = false; cancelAnimationFrame(raf); }
  const manual = i => { touched = true; pause(); go(i); bars[stage].style.setProperty('--p', 1); };

  function setMode(m) {
    mode = m === 'cn' ? 'cn' : 'kr';
    box.classList.toggle('land', mode === 'cn');
    $$('[data-vy-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.vyMode === mode)));
    render();
  }

  // сцена порта: at — показать точку пути, run — пройти путь заново
  const at = v => Math.max(0, Math.min(4, Math.round(v * 4)));
  window.RenalRoute = {
    at: v => { pause(); touched = true; go(at(v)); bars[stage].style.setProperty('--p', 1); },
    run: (a) => { touched = false; pause(); go(at(a)); if (visible) play(); },
  };

  new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) play(); else pause(); }, {threshold: .45}).observe(box);
  $$('[data-vy-step]').forEach(b => b.addEventListener('click', () => manual(+b.dataset.vyStep)));
  $('[data-tk-prev]').addEventListener('click', () => manual(stage - 1));
  $('[data-tk-next]').addEventListener('click', () => manual(stage + 1));
  $$('[data-vy-mode]').forEach(b => b.addEventListener('click', () => { setMode(b.dataset.vyMode); touched = false; pause(); go(0); play(); }));
  // свайп по фото
  let sx = null;
  stageEl.addEventListener('touchstart', e => { sx = e.touches[0].clientX; }, {passive: true});
  stageEl.addEventListener('touchend', e => {
    if (sx === null) return;
    const dx = e.changedTouches[0].clientX - sx; sx = null;
    if (Math.abs(dx) > 40) manual(stage + (dx < 0 ? 1 : -1));
  });

  addEventListener('renal:car', e => {
    const {title, country, turnkey, manual: hand} = e.detail || {};
    if (!title) return;
    box.classList.add('picked');
    carEl.innerHTML = `<b></b> — ${country === 'cn' ? 'из Китая по суше' : 'из Кореи морем'}` +
      `${turnkey ? `, ≈ ${Math.round(turnkey).toLocaleString('ru-RU')} ₽ с растаможкой` : ''}`;
    carEl.querySelector('b').textContent = title;
    setMode(country);
    if (!hand) { touched = false; pause(); go(0); play(); }
  });

  setMode('kr');
})();
