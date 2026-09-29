(() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

  // --- заявки --------------------------------------------------------------
  document.querySelectorAll('form[data-lead]').forEach(form => {
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const msg = form.querySelector('.form-msg');
      const data = Object.fromEntries(new FormData(form).entries());
      for (const k of Object.keys(data)) if (data[k] === '') delete data[k];
      if (!data.phone && !data.telegram) {
        msg.innerHTML = '<p class="error">Укажите телефон или Telegram, чтобы менеджер мог ответить.</p>';
        return;
      }
      if (data.budget_rub) data.budget_rub = parseInt(data.budget_rub, 10);
      data.page = location.pathname;
      const btn = form.querySelector('button[type=submit]');
      btn.disabled = true;
      try {
        const res = await fetch('/api/leads', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.detail && typeof body.detail === 'string' ? body.detail : 'Не удалось отправить');
        form.innerHTML = '<div class="thanks">Заявка отправлена! Менеджер свяжется с вами в ближайшее время.</div>';
        if (window.ym && window.YM_ID) window.ym(window.YM_ID, 'reachGoal', 'lead');
      } catch (err) {
        msg.innerHTML = `<p class="error">${esc(err.message)}. Попробуйте ещё раз.</p>`;
        btn.disabled = false;
      }
    });
  });

  // --- галерея -------------------------------------------------------------
  const main = document.getElementById('main-photo');
  document.querySelectorAll('[data-photo]').forEach(btn => btn.addEventListener('click', () => {
    main.src = btn.dataset.photo;
    document.querySelectorAll('[data-photo]').forEach(b => b.classList.toggle('on', b === btn));
  }));

  // --- проверка VIN --------------------------------------------------------
  const labels = {ok: 'Явных проблем не найдено', warning: 'Есть замечания', danger: 'Есть серьёзные проблемы'};
  function renderReport(r) {
    const d = r.decoded;
    const items = r.checks.map(c => `<div class="item ${c.severity}">${esc(c.detail)}</div>`).join('');
    const h = r.history;
    const hist = h ? `<h3>История (${esc(h.source)})</h3>
      <div class="item ${h.flags && h.flags.length ? 'danger' : 'info'}">ДТП: по своей вине ${h.accidents_own}, по чужой ${h.accidents_other} ·
      смен владельца ${h.owner_changes}${h.accident_cost_own_krw ? ' · выплаты ' + h.accident_cost_own_krw.toLocaleString('ru-RU') + ' ₩' : ''}</div>` : '';
    const nhtsa = r.external && r.external.nhtsa && Object.keys(r.external.nhtsa).length
      ? `<div class="item info">NHTSA: ${esc(Object.entries(r.external.nhtsa).filter(([k]) => !k.startsWith('Error')).map(([k, v]) => k + ': ' + v).join(', '))}</div>` : '';
    const seen = r.listings && r.listings.length
      ? `<div class="item info">В нашей базе объявлений: ${r.listings.length}</div>` : '';
    return `<p class="verdict ${r.verdict === 'danger' ? 'bad' : r.verdict === 'warning' ? 'warn' : 'ok'}">${labels[r.verdict]}</p>
      <p><code>${esc(r.vin)}</code> · ${esc(d.country || 'страна не определена')} · ${esc(d.manufacturer || 'производитель не определён')}
      ${d.model_year ? ' · модельный год ' + d.model_year : ''}</p>${items}${hist}${nhtsa}${seen}`;
  }
  async function showReport(url) {
    const box = document.getElementById('report');
    box.innerHTML = '<p class="muted">Проверяем…</p>';
    try {
      const res = await fetch(url);
      const body = await res.json();
      box.innerHTML = res.ok ? renderReport(body) : `<p class="error">${esc(body.detail)}</p>`;
    } catch (err) {
      box.innerHTML = '<p class="error">Не удалось выполнить проверку. Попробуйте позже.</p>';
    }
  }
  document.querySelectorAll('[data-vin-report]').forEach(b => b.addEventListener('click', () => showReport(b.dataset.vinReport)));
  document.querySelectorAll('form[data-vin-form]').forEach(f => f.addEventListener('submit', e => {
    e.preventDefault();
    const vin = new FormData(f).get('vin').trim();
    if (vin) showReport('/api/vin/' + encodeURIComponent(vin));
  }));

  // --- живая лента -----------------------------------------------------------
  const grid = document.getElementById('grid');
  if (grid && window.EventSource) {
    const dot = document.getElementById('live-dot'), text = document.getElementById('live-text');
    const es = new EventSource('/api/stream?' + (grid.dataset.stream || ''));
    let added = 0;
    es.onopen = () => { dot.classList.add('on'); text.textContent = 'Новые объявления появляются здесь автоматически'; };
    es.onerror = () => { dot.classList.remove('on'); text.textContent = 'Переподключаемся…'; };
    es.addEventListener('new', async e => {
      const ev = JSON.parse(e.data);
      const l = ev.listing;
      if (grid.querySelector(`[data-key="${CSS.escape(l.source + ':' + l.external_id)}"]`)) return;
      const res = await fetch(`/partials/card/${encodeURIComponent(l.source)}/${encodeURIComponent(l.external_id)}${location.search}`);
      if (res.status !== 200) return;
      const tpl = document.createElement('template');
      tpl.innerHTML = (await res.text()).trim();
      if (tpl.content.firstElementChild) {
        grid.prepend(tpl.content.firstElementChild);
        added += 1;
        text.textContent = `Новых объявлений с момента открытия: ${added}`;
      }
    });
  }
})();
