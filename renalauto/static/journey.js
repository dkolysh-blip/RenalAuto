// Блок «Путь машины»: сцена прилипает к экрану, прокрутка ведёт судно из Пусана и автовоз из Харбина
// во Владивосток, там — таможня и документы, дальше автовоз уходит в ваш город.
// Машина, выбранная на стоянке, едет на борту (событие renal:car из port.js).
(() => {
  const box = document.querySelector('[data-journey]');
  if (!box) return;
  const $ = s => box.querySelector(s);
  const steps = [...box.querySelectorAll('[data-j-step]')];
  const stamps = [...box.querySelectorAll('[data-j-stamps] li')];
  const bar = $('[data-j-bar]');
  const hud = {step: $('[data-j-hud-step]'), title: $('[data-j-hud-title]'), car: $('[data-j-hud-car]')};
  const route = id => {
    const path = $(`[data-j-path="${id}"]`), len = path.getTotalLength();
    path.style.strokeDasharray = `${len}`;
    return {id, path, len, veh: $(`[data-j-veh="${id}"]`), pt: $(`[data-j-pt="${id}"]`)};
  };
  const R = {kr: route('kr'), cn: route('cn'), ru: route('ru')};
  const hub = $('[data-j-pt="vl"]');
  // этапы: [начало, заголовок]; доли прокрутки подобраны под длину маршрутов
  const PHASES = [[0, 'Выкуп и проверка'], [0.12, 'Экспорт'], [0.5, 'Владивосток'], [0.68, 'В ваш город'], [0.93, 'Ключи у вас']];
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
  const ease = t => t < .5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
  let country = null;  // 'kr' | 'cn' — откуда выбранная машина; null — показываем оба пути

  function place(r, t) {
    r.path.style.strokeDashoffset = `${r.len * (1 - t)}`;
    const L = r.len * t, a = r.path.getPointAtLength(Math.max(0, L - 1)), b = r.path.getPointAtLength(Math.min(r.len, L + 1));
    const p = r.path.getPointAtLength(L);
    const ang = Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI;
    r.veh.setAttribute('transform', `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)}) rotate(${ang.toFixed(1)})`);
  }

  function render(p) {
    const phase = PHASES.filter(([t]) => p >= t).length - 1;
    const exp = ease(clamp((p - 0.12) / 0.38)), ru = ease(clamp((p - 0.68) / 0.25));
    place(R.kr, exp); place(R.cn, exp); place(R.ru, ru);
    // из Владивостока дальше едет одна машина: та, что выбрана, иначе — с судна
    // во Владивостоке судно и автовоз сдают машину: дальше её везёт автовоз по России
    R.kr.veh.classList.toggle('off', p >= 0.52);
    R.cn.veh.classList.toggle('off', p >= 0.52);
    R.ru.veh.classList.toggle('off', p < 0.52);
    for (const id of ['kr', 'cn']) {
      const other = country && country !== id;
      R[id].path.classList.toggle('dim', other); R[id].veh.classList.toggle('dim', other); R[id].pt.classList.toggle('dim', other);
      R[id].pt.classList.toggle('live', phase === 0 && !other);
    }
    hub.classList.toggle('live', phase === 2);
    const st = clamp((p - 0.52) / 0.14);
    stamps.forEach((s, i) => s.classList.toggle('on', phase >= 2 && st > i / stamps.length));
    stamps[0].parentElement.classList.toggle('past', phase > 2);
    steps.forEach((s, i) => { s.classList.toggle('done', i < phase); s.classList.toggle('on', i === phase); });
    hud.step.textContent = `Этап ${phase + 1} из ${PHASES.length}`;
    hud.title.textContent = PHASES[phase][1];
    bar.style.width = `${(p * 100).toFixed(1)}%`;
  }

  // выбранная машина: её спрайт на борту судна (или на автовозе из Китая) и дальше — на автовозе по России
  addEventListener('renal:car', e => {
    const {sprite, title, country: c} = e.detail || {};
    if (!sprite) return;
    country = c === 'cn' ? 'cn' : 'kr';
    box.querySelector(`[data-j-mine="${country}"]`)?.setAttribute('href', sprite);
    box.querySelector('[data-j-mine="ru"]')?.setAttribute('href', sprite);
    hud.car.textContent = `${country === 'cn' ? 'Едет' : 'На борту'}: ${title}`;
    hud.car.hidden = false;
    update();
  });

  if (matchMedia('(prefers-reduced-motion: reduce)').matches) { render(1); return; }
  const track = $('.journey-track'), stage = $('.journey-stage');
  let ticking = false;
  function update() {
    ticking = false;
    const r = track.getBoundingClientRect();
    // путь проходится, пока сцена прилипла: от верха трека до его низа минус высота сцены
    const top = parseFloat(getComputedStyle(stage).top) || 0;
    render(clamp((top - r.top) / Math.max(1, r.height - stage.offsetHeight)));
  }
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, {passive: true});
  addEventListener('resize', update);
  update();
})();
