// Подсказки города в формах заявки: список крупных городов России, подходят по началу названия или любого его слова.
// Работает на любом поле name="city"; свой город можно вписать и без подсказки.
(() => {
  const CITIES = ['Москва', 'Санкт-Петербург', 'Новосибирск', 'Екатеринбург', 'Казань', 'Нижний Новгород', 'Челябинск', 'Красноярск',
    'Самара', 'Уфа', 'Ростов-на-Дону', 'Краснодар', 'Омск', 'Воронеж', 'Пермь', 'Волгоград', 'Саратов', 'Тюмень', 'Тольятти', 'Махачкала',
    'Барнаул', 'Ижевск', 'Хабаровск', 'Ульяновск', 'Иркутск', 'Владивосток', 'Ярославль', 'Севастополь', 'Томск', 'Ставрополь', 'Кемерово',
    'Набережные Челны', 'Оренбург', 'Новокузнецк', 'Балашиха', 'Рязань', 'Чебоксары', 'Калининград', 'Пенза', 'Липецк', 'Киров', 'Астрахань',
    'Тула', 'Улан-Удэ', 'Сочи', 'Курск', 'Магнитогорск', 'Тверь', 'Иваново', 'Брянск', 'Белгород', 'Сургут', 'Владимир', 'Чита', 'Архангельск',
    'Нижний Тагил', 'Калуга', 'Симферополь', 'Якутск', 'Смоленск', 'Волжский', 'Курган', 'Орёл', 'Череповец', 'Вологда', 'Саранск',
    'Владикавказ', 'Мурманск', 'Подольск', 'Тамбов', 'Грозный', 'Стерлитамак', 'Петрозаводск', 'Кострома', 'Нижневартовск', 'Новороссийск',
    'Йошкар-Ола', 'Химки', 'Таганрог', 'Комсомольск-на-Амуре', 'Сыктывкар', 'Нальчик', 'Шахты', 'Дзержинск', 'Энгельс', 'Благовещенск',
    'Братск', 'Великий Новгород', 'Старый Оскол', 'Королёв', 'Псков', 'Бийск', 'Люберцы', 'Мытищи', 'Прокопьевск', 'Южно-Сахалинск',
    'Балаково', 'Армавир', 'Рыбинск', 'Северодвинск', 'Абакан', 'Петропавловск-Камчатский', 'Норильск', 'Сызрань', 'Волгодонск',
    'Уссурийск', 'Каменск-Уральский', 'Новочеркасск', 'Златоуст', 'Электросталь', 'Альметьевск', 'Салават', 'Миасс', 'Керчь', 'Находка',
    'Копейск', 'Пятигорск', 'Хасавюрт', 'Рубцовск', 'Березники', 'Коломна', 'Майкоп', 'Одинцово', 'Ковров', 'Красногорск', 'Кисловодск',
    'Нефтекамск', 'Нефтеюганск', 'Новочебоксарск', 'Серпухов', 'Щёлково', 'Дербент', 'Черкесск', 'Батайск', 'Новомосковск', 'Орск',
    'Новый Уренгой', 'Ноябрьск', 'Артём', 'Октябрьский', 'Димитровград', 'Камышин', 'Муром', 'Ессентуки', 'Невинномысск', 'Обнинск',
    'Евпатория', 'Ачинск', 'Елец', 'Сергиев Посад', 'Арзамас', 'Междуреченск', 'Магадан', 'Анадырь', 'Биробиджан', 'Ангарск', 'Евпатория',
    'Ханты-Мансийск', 'Салехард', 'Горно-Алтайск', 'Кызыл', 'Элиста', 'Нарьян-Мар', 'Арсеньев', 'Спасск-Дальний', 'Партизанск', 'Дальнегорск',
    'Большой Камень', 'Лесозаводск', 'Свободный', 'Белогорск', 'Тында', 'Нерюнгри', 'Мирный', 'Амурск', 'Советская Гавань', 'Ванино',
    'Корсаков', 'Холмск', 'Усть-Илимск', 'Тобольск', 'Ишим', 'Когалым', 'Мегион', 'Лабытнанги', 'Надым', 'Усинск', 'Воркута', 'Ухта'];
  const LIST = [...new Set(CITIES)];
  const norm = s => s.toLowerCase().replace(/ё/g, 'е');
  function suggest(q) {
    q = norm(q.trim());
    if (!q) return [];
    const starts = [], words = [];
    for (const c of LIST) {
      const n = norm(c);
      if (n.startsWith(q)) starts.push(c);
      else if (n.split(/[\s-]+/).some(w => w.startsWith(q))) words.push(c);
    }
    return [...starts, ...words].slice(0, 6);
  }
  // обработчики — на документе: форма заявки после отправки пересобирается, поля появляются заново
  let uid = 0;
  const state = new WeakMap();
  function setup(input) {
    if (state.has(input)) return state.get(input);
    let list = input.parentNode.classList.contains('city-box') ? input.parentNode.querySelector('.city-list') : null;
    if (!list) {
      const box = document.createElement('div');
      box.className = 'city-box';
      input.parentNode.insertBefore(box, input);
      box.appendChild(input);
      list = document.createElement('ul');
      list.className = 'city-list';
      list.setAttribute('role', 'listbox');
      box.appendChild(list);
    }
    list.id = `city-list-${++uid}`;
    list.hidden = true;
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-controls', list.id);
    input.setAttribute('aria-expanded', 'false');
    const st = {list, items: [], active: -1};
    list.addEventListener('mousedown', e => {
      const li = e.target.closest('li');
      if (!li) return;
      e.preventDefault();
      pick(input, st.items[[...list.children].indexOf(li)]);
    });
    state.set(input, st);
    return st;
  }
  function close(input) {
    const st = state.get(input);
    if (!st) return;
    st.list.hidden = true; st.active = -1;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
  }
  function mark(input, i) {
    const st = state.get(input);
    st.active = i;
    [...st.list.children].forEach((li, k) => li.setAttribute('aria-selected', String(k === i)));
    if (i >= 0) input.setAttribute('aria-activedescendant', `${st.list.id}-${i}`);
  }
  function pick(input, c) { input.value = c; close(input); }
  function render(input) {
    const st = setup(input);
    st.items = suggest(input.value);
    if (!st.items.length || (st.items.length === 1 && norm(st.items[0]) === norm(input.value.trim()))) { close(input); return; }
    const q = input.value.trim(), nq = norm(q);
    st.list.innerHTML = st.items.map((c, i) => `<li role="option" id="${st.list.id}-${i}" aria-selected="false">${
      norm(c).startsWith(nq) ? `<b>${c.slice(0, q.length)}</b>${c.slice(q.length)}` : c}</li>`).join('');
    st.list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    mark(input, -1);
  }
  const isCity = el => el && el.matches && el.matches('input[name="city"]');
  document.querySelectorAll('input[name="city"]').forEach(setup);
  document.addEventListener('input', e => { if (isCity(e.target)) render(e.target); });
  document.addEventListener('focusin', e => { if (isCity(e.target)) { setup(e.target); if (e.target.value) render(e.target); } });
  document.addEventListener('focusout', e => { if (isCity(e.target)) setTimeout(() => close(e.target), 100); });
  document.addEventListener('keydown', e => {
    const input = e.target, st = isCity(input) && state.get(input);
    if (!st || st.list.hidden) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      mark(input, (st.active + (e.key === 'ArrowDown' ? 1 : -1) + st.items.length) % st.items.length);
    } else if (e.key === 'Enter' && st.active >= 0) { e.preventDefault(); pick(input, st.items[st.active]); }
    else if (e.key === 'Escape') close(input);
  });

  // телефон: +7 (914) 066-88-08 по мере ввода; номер не из России оставляем как есть
  document.addEventListener('input', e => {
    const input = e.target;
    if (!input.matches || !input.matches('form[data-lead] input[type="tel"]')) return;
    if (e.inputType && e.inputType.startsWith('delete')) return;  // стирание не переформатируем, иначе скобку не удалить
    let d = input.value.replace(/\D/g, '');
    if (!d) { input.value = ''; return; }
    if (input.value.trim().startsWith('+') && d[0] !== '7') return;
    if (d[0] === '8') d = '7' + d.slice(1);
    if (d[0] !== '7') d = '7' + d;
    d = d.slice(0, 11);
    const p = [d.slice(1, 4), d.slice(4, 7), d.slice(7, 9), d.slice(9, 11)];
    input.value = '+7' + (p[0] ? ` (${p[0]}` : '') + (p[0].length === 3 ? ')' : '') + (p[1] ? ` ${p[1]}` : '') +
      (p[2] ? `-${p[2]}` : '') + (p[3] ? `-${p[3]}` : '');
  });
})();
