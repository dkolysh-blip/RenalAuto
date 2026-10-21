// Калькулятор цены под ключ на лендинге: считает сервер (/api/calc), здесь — только форма и вывод.
(() => {
  const form = document.querySelector('form[data-calc]');
  if (!form) return;
  const box = form.parentElement;
  const verdict = box.querySelector('[data-calc-verdict]');
  const lines = box.querySelector('[data-calc-lines]');
  const total = box.querySelector('[data-calc-total]');
  const cta = box.querySelector('[data-calc-cta]');
  const rub = n => Math.round(n).toLocaleString('ru-RU') + ' ₽';
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  let timer = 0, seq = 0, last = null;

  async function run() {
    const params = new URLSearchParams(new FormData(form));
    if (!(+params.get('price') > 0)) return;
    const my = ++seq;
    try {
      const res = await fetch('/api/calc?' + params);
      const r = await res.json();
      if (my !== seq) return;
      if (!res.ok) throw new Error(typeof r.detail === 'string' ? r.detail : 'Проверьте параметры');
      last = {params, r};
      verdict.className = 'calc-verdict ' + (r.passable ? 'ok' : 'bad');
      verdict.textContent = (r.passable ? '✓ ' : '✕ ') + r.verdict;
      lines.innerHTML = r.lines.map(l => `<tr><th>${esc(l.title)}${l.note ? `<small>${esc(l.note)}</small>` : ''}</th>
        <td>${l.rub === null ? '—' : (l.note === 'от этой суммы' ? 'от ' : '') + rub(l.rub)}</td></tr>`).join('');
      total.textContent = (r.total_is_from ? 'от ' : '') + rub(r.total_rub);
    } catch (err) {
      if (my === seq) verdict.textContent = err.message;
    }
  }
  form.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(run, 250); });
  // на телефоне ручные параметры свёрнуты: их заполняет выбор марки и модели
  const more = form.querySelector('[data-calc-more]');
  if (more && matchMedia('(max-width: 760px)').matches) more.open = false;
  form.addEventListener('submit', e => e.preventDefault());

  // «Получить точный расчёт»: подставляем параметры в комментарий формы подбора
  cta.addEventListener('click', () => {
    const comment = document.querySelector('#podbor textarea[name="comment"]');
    if (!comment || !last) return;
    const p = last.params, label = s => form.querySelector(`input[name="${s}"]:checked`)?.parentElement.textContent.trim();
    comment.value = `Расчёт из калькулятора: ${label('country')}, ${label('engine')}, ${label('age')}, ` +
      `${p.get('cc')} см³, ${p.get('hp')} л.с., цена ${p.get('price')} ${p.get('currency')} — ` +
      `ориентировочно ${total.textContent} под ключ.`;
    setTimeout(() => document.querySelector('#podbor input[name="name"]')?.focus({preventScroll: true}), 400);
  });
  // Марка → модель → год из свежих объявлений: подставляем страну, двигатель, объём и типичную цену за год
  const pickEl = {make: form.querySelector('[data-calc-make]'), model: form.querySelector('[data-calc-model]'),
    year: form.querySelector('[data-calc-year]'), info: form.querySelector('[data-calc-info]')};
  const showBtn = box.querySelector('[data-calc-show]');
  const showText = showBtn?.textContent;
  let catalog = [], chosen = null;
  const plural = (n, a, b, c) => n % 10 === 1 && n % 100 !== 11 ? a : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? b : c;
  const opts = (sel, items, empty) => {
    sel.innerHTML = `<option value="">${empty}</option>` + items.map(([v, t]) => `<option value="${esc(v)}">${esc(t)}</option>`).join('');
    sel.disabled = !items.length;
  };
  const setVal = (name, value) => { const el = form.elements[name]; if (el) el.value = value; };
  function choose() {
    const mk = catalog.find(m => m.make === pickEl.make.value);
    const md = mk?.models.find(m => m.model === pickEl.model.value);
    chosen = md ? {make: mk.make, model: md.model, ...md} : null;
    if (showBtn) showBtn.textContent = chosen ? `Показать ${chosen.make} ${chosen.model} на стоянке` : showText;
    if (!chosen) {
      pickEl.info.textContent = mk ? `${mk.make}: ${mk.count} ${plural(mk.count, 'объявление', 'объявления', 'объявлений')} в ленте — выберите модель.`
        : 'Выберите машину из объявлений — подставим её параметры и цену. Или задайте всё вручную ниже.';
      return;
    }
    const y = pickEl.year.value || Object.keys(chosen.years).sort().pop();
    const yr = chosen.years[y];
    const age = new Date().getFullYear() - +y;
    setVal('country', chosen.country); setVal('engine', chosen.engine);
    setVal('age', age < 3 ? 'new' : age <= 5 ? 'mid' : 'old');
    if (chosen.cc) setVal('cc', chosen.cc);
    setVal('price', yr.price); setVal('currency', 'RUB');
    picked.hidden = true;
    pickEl.info.innerHTML = `<b>${esc(chosen.make)} ${esc(chosen.model)} ${y}</b>: ${yr.n} ${plural(yr.n, 'объявление', 'объявления', 'объявлений')} в ленте, ` +
      `цена машины — типичная за этот год. Мощность в объявлениях не указана — проверьте поле «Мощность». <button type="button" data-calc-reset>Сбросить</button>`;
    run();
  }
  pickEl.make.addEventListener('change', () => {
    const mk = catalog.find(m => m.make === pickEl.make.value);
    opts(pickEl.model, mk ? mk.models.map(m => [m.model, `${m.model} (${m.count})`]) : [], mk ? 'Выберите модель' : 'Модель');
    opts(pickEl.year, [], '—');
    choose();
  });
  pickEl.model.addEventListener('change', () => {
    const md = catalog.find(m => m.make === pickEl.make.value)?.models.find(m => m.model === pickEl.model.value);
    opts(pickEl.year, md ? Object.entries(md.years).sort((a, b) => b[0] - a[0]).map(([y, v]) => [y, `${y} (${v.n})`]) : [], md ? 'Любой' : '—');
    choose();
  });
  pickEl.year.addEventListener('change', choose);
  pickEl.info.addEventListener('click', e => { if (e.target.closest('[data-calc-reset]')) resetPick(); });
  function resetPick() {
    pickEl.make.value = '';
    pickEl.make.dispatchEvent(new Event('change'));
  }
  fetch('/api/port/models').then(r => r.json()).then(data => {
    catalog = data.makes || [];
    opts(pickEl.make, catalog.map(m => [m.make, `${m.make} (${m.count})`]), 'Все марки');
    // message match: ?model=k5 из рекламы — сразу эта модель
    let match = null;
    try { match = JSON.parse(document.getElementById('port-data')?.textContent || '{}').match; } catch (_) { /* без сцены */ }
    if (match) {
      const low = match.toLowerCase();
      for (const mk of catalog) {
        const md = mk.models.find(m => `${mk.make} ${m.model}`.toLowerCase() === low || m.model.toLowerCase() === low);
        if (md) { pickEl.make.value = mk.make; pickEl.make.dispatchEvent(new Event('change'));
          pickEl.model.value = md.model; pickEl.model.dispatchEvent(new Event('change')); break; }
      }
    }
  }).catch(() => { pickEl.info.textContent = 'Задайте параметры машины вручную.'; });

  // «Показать машины в этом бюджете»: пульт терминала получает бюджет (или выбранную модель), терминал переезжает на нужную стоянку
  showBtn?.addEventListener('click', () => {
    const pf = document.querySelector('form[data-port-filter]');
    if (!pf || !last) return;
    const sel = pf.elements.budget, sum = last.r.total_rub;
    if (chosen) {
      sel.value = '';
      if (pf.elements.q) pf.elements.q.value = `${chosen.make} ${chosen.model}`;
    } else {
      const opt = [...sel.options].find(o => o.value && +o.value >= sum);
      sel.value = opt ? opt.value : '';
    }
    pf.elements.country.value = last.params.get('country') || '';
    pf.dispatchEvent(new Event('input', {bubbles: true}));
    document.getElementById('terminal')?.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center'});
  });

  // Терминал передаёт сюда машину: калькулятор заполняется её параметрами
  const picked = document.createElement('div');
  picked.className = 'calc-picked';
  picked.hidden = true;
  box.querySelector('.calc-result').prepend(picked);
  picked.addEventListener('click', e => { if (e.target.closest('button')) picked.hidden = true; });
  window.RenalCalc = {
    fill(c, title) {
      if (pickEl.make.value) { pickEl.make.value = ''; opts(pickEl.model, [], 'Модель'); opts(pickEl.year, [], '—'); chosen = null;
        if (showBtn) showBtn.textContent = showText; }
      const set = (name, value) => {
        const el = form.elements[name];
        if (el instanceof RadioNodeList) el.value = value; else if (el) el.value = value;
      };
      set('country', c.country); set('engine', c.engine); set('age', c.age);
      set('cc', c.cc); set('price', c.price); set('currency', 'RUB');
      picked.innerHTML = `<span>Выбранная машина: <b>${esc(title)}</b>. Мощность в объявлении не указана — проверьте поле «Мощность».</span><button type="button" aria-label="Убрать">×</button>`;
      picked.hidden = false;
      if (more) more.open = true;
      form.elements.hp.classList.add('attn');
      setTimeout(() => form.elements.hp.classList.remove('attn'), 2400);
      run();
      document.getElementById('calc').scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
    },
  };
  run();
})();
