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
  run();
})();
