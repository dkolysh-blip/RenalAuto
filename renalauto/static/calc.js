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
  // «Показать машины в этом бюджете»: пульт терминала получает бюджет, терминал переезжает на нужную стоянку
  box.querySelector('[data-calc-show]')?.addEventListener('click', () => {
    const pf = document.querySelector('form[data-port-filter]');
    if (!pf || !last) return;
    const sel = pf.elements.budget, sum = last.r.total_rub;
    const opt = [...sel.options].find(o => o.value && +o.value >= sum);
    sel.value = opt ? opt.value : '';
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
      const set = (name, value) => {
        const el = form.elements[name];
        if (el instanceof RadioNodeList) el.value = value; else if (el) el.value = value;
      };
      set('country', c.country); set('engine', c.engine); set('age', c.age);
      set('cc', c.cc); set('price', c.price); set('currency', 'RUB');
      picked.innerHTML = `<span>Выбранная машина: <b>${esc(title)}</b>. Мощность в объявлении не указана — проверьте поле «Мощность».</span><button type="button" aria-label="Убрать">×</button>`;
      picked.hidden = false;
      form.elements.hp.classList.add('attn');
      setTimeout(() => form.elements.hp.classList.remove('attn'), 2400);
      run();
      document.getElementById('calc').scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
    },
  };
  run();
})();
