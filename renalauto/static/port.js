// Сцена «Порт» на лендинге: объявления из живой ленты — машины, которые заезжают на терминал.
// Сцена декоративная (aria-hidden) и стартует после загрузки страницы: без неё лендинг работает полностью.
(() => {
  const root = document.getElementById('terminal');
  const dataEl = document.getElementById('port-data');
  if (!root || !dataEl) return;
  const NS = 'http://www.w3.org/2000/svg';
  const ASSETS = '/static/port', V = '11';  // V — поднять после перерендера
  // Порт всегда дневной: светлая сцена продаёт лучше. Ночная подложка — только по ?night=1
  const NIGHT = new URLSearchParams(location.search).get('night') === '1';
  const PLATE = NIGHT ? '-night' : '';
  const DATA = JSON.parse(dataEl.textContent);
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const goal = name => { if (window.ym && window.YM_ID) window.ym(window.YM_ID, 'reachGoal', name); };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const rnd = (a, b) => a + Math.random() * (b - a);
  const pick = arr => arr[Math.floor(Math.random() * arr.length)];
  const label = d => `${d.title}${d.year ? ' ' + d.year : ''}`;
  const rub = n => Math.round(n).toLocaleString('ru-RU').replace(/,/g, ' ');
  const mln = n => (n / 1e6).toFixed(n < 1e7 ? 2 : 1).replace(/0$/, '').replace('.', ',') + ' млн ₽';

  // ролик с выдач: без звука играет, пока виден на экране; звук — по кнопке
  const reel = document.querySelector('[data-reel]');
  if (reel) {
    const v = reel.querySelector('video'), snd = reel.querySelector('[data-reel-sound]');
    const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
    new IntersectionObserver(([e]) => {
      if (e.isIntersecting && (!still || !v.muted)) v.play().catch(() => {}); else if (!e.isIntersecting) v.pause();
    }, {threshold: .4}).observe(reel);
    snd.addEventListener('click', () => {
      v.muted = !v.muted;
      if (!v.muted) { v.currentTime = 0; v.play().catch(() => {}); goal('video'); }
      snd.setAttribute('aria-pressed', String(!v.muted));
      snd.textContent = v.muted ? 'Включить звук' : 'Выключить звук';
    });
  }

  // фото с выдач: по нажатию — во весь экран с подписью, откуда фото
  const shotDlg = document.getElementById('shot-dialog');
  if (shotDlg) {
    document.querySelectorAll('[data-shot]').forEach(b => b.addEventListener('click', () => {
      shotDlg.querySelector('img').src = b.dataset.shot;
      shotDlg.querySelector('img').alt = b.dataset.shotCap;
      shotDlg.querySelector('p').textContent = b.dataset.shotCap;
      shotDlg.showModal(); goal('photo');
    }));
    shotDlg.addEventListener('click', e => { if (e.target === shotDlg || e.target.closest('[data-close]')) shotDlg.close(); });
  }

  // карусель отзывов: свайп или стрелки, сама листается раз в 7 секунд, пока её не трогают
  const rv = document.querySelector('[data-rv]');
  if (rv) {
    const track = rv.querySelector('[data-rv-track]'), cards = [...track.children], count = rv.querySelector('[data-rv-count]');
    // «Читать полностью» — только у отзывов, которые не влезли в карточку
    const fit = () => cards.forEach(c => {
      const t = c.querySelector('[data-rv-text]'), b = c.querySelector('[data-rv-more]');
      if (!c.classList.contains('open')) b.hidden = t.scrollHeight <= t.clientHeight + 2;
    });
    track.addEventListener('click', e => {
      const b = e.target.closest('[data-rv-more]');
      if (!b) return;
      const c = b.closest('.rv-card'), open = c.classList.toggle('open');
      b.textContent = open ? 'Свернуть' : 'Читать полностью';
      stop();
    });
    fit(); addEventListener('resize', fit);
    const step = () => cards[0].offsetWidth + parseFloat(getComputedStyle(track).columnGap || 0);
    const at = () => Math.round(track.scrollLeft / step());
    const perView = () => Math.max(1, Math.round(track.clientWidth / step()));
    const go = i => track.scrollTo({left: i * step(), behavior: 'smooth'});
    const upd = () => { count.textContent = `${Math.min(cards.length, at() + perView())} из ${cards.length}`; };
    const next = () => go(at() + perView() >= cards.length ? 0 : at() + 1);
    rv.querySelector('[data-rv-next]').addEventListener('click', () => { stop(); next(); });
    rv.querySelector('[data-rv-prev]').addEventListener('click', () => { stop(); go(Math.max(0, at() - 1)); });
    track.addEventListener('scroll', () => requestAnimationFrame(upd), {passive: true});
    let timer = 0, seen = false;
    const stop = () => { clearInterval(timer); timer = -1; };
    ['pointerdown', 'focusin', 'wheel'].forEach(ev => track.addEventListener(ev, stop, {passive: true}));
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
      new IntersectionObserver(([e]) => {
        if (timer === -1) return;
        clearInterval(timer); timer = e.isIntersecting ? setInterval(next, 7000) : 0;
        seen = seen || e.isIntersecting;
      }, {threshold: .5}).observe(rv);
      rv.addEventListener('mouseenter', () => { if (timer > 0) clearInterval(timer); });
      rv.addEventListener('mouseleave', () => { if (timer > 0) timer = setInterval(next, 7000); });
    }
    upd(); addEventListener('resize', upd);
  }
  document.querySelectorAll('[data-goal]').forEach(a => a.addEventListener('click', () => goal(a.dataset.goal)));

  // --- раскладка терминала ----------------------------------------------------
  // Две раскладки: широкая (десктоп) и узкая вертикальная полоса в 2 ряда (телефон), судно внизу.
  // Каждое место: где стоит машина и три маршрута — заезд через ворота, выезд обратно и путь к рампе.
  function wideLayout() {
    const W = 1600, H = 760, road = 56, apron = 540, quay = 600, rampX = 410, ZW = 760, COLS = 14;  // паром — у корейской стоянки
    const rows = [[164, 214], [266, 214], [344, 394], [446, 394]];  // центр мест и их проезд
    const zones = [{zone: 'KR', x0: 30}, {zone: 'CN', x0: 810}];
    const slots = [];
    for (const z of zones) {
      const cx = z.x0 + 24;
      for (const [sy, a] of rows) for (let i = 0; i < COLS; i++) {
        const sx = z.x0 + 76 + i * 50;
        slots.push({
          zone: z.zone, x: sx, y: sy, col: i,
          chip: [sx, sy + (a > sy ? 32 : -32)],  // ценник — на асфальте у въезда на место
          in: [[-60, road], [cx, road], [cx, a], [sx, a], [sx, sy]],
          out: [[sx, sy], [sx, a], [cx, a], [cx, road], [-60, road]],
          ramp: z.zone === 'CN' ? [[sx, sy], [sx, a], [cx, a], [cx, road + 36]]  // Китай — к дороге, там забирает автовоз
            : [[sx, sy], [sx, a], [cx, a], [cx, apron], [rampX, apron], [rampX, quay + 34]],
        });
      }
    }
    return {
      W, H, slots, quay, rampX, cols: COLS, zoom: 1.9, ship: {x: 60, y: quay + 26, w: 700, h: 115},
      cranes: [130, 690].map(x => ({x, y0: quay - 84, y1: quay + 160})), truck: road + 9,
      zones: zones.map(z => ({zone: z.zone, title: [z.x0 + 52, 124], stats: [z.x0 + ZW - 10, 124],
        scale: {x0: z.x0 + 76, x1: z.x0 + 76 + (COLS - 1) * 50, y: 500}})),
      paint(g) {
        g.innerHTML = `<image href="${ASSETS}/yard-wide${PLATE}.webp?v=${V}" width="${W}" height="${H}" preserveAspectRatio="none"/>
          ${zones.map(z => `${flag(z.zone, z.x0 + 52, 124)}<text x="${z.x0 + 80}" y="124" class="t-zone">${z.zone === 'KR' ? 'КОРЕЯ' : 'КИТАЙ'}</text>`).join('')}
          ${barrier(28, road, 'v')}`;
      },
    };
  }

  function narrowLayout() {
    const W = 360, H = 650, lane = 180, quay = 556;
    const zones = [{zone: 'KR', y0: 56}, {zone: 'CN', y0: 304}];
    const slots = [];
    for (const z of zones) for (let j = 0; j < 7; j++) for (const side of [-1, 1]) {
      const sy = z.y0 + 36 + j * 30, sx = lane + side * 60;
      slots.push({
        zone: z.zone, x: sx, y: sy, col: j,
        chip: [lane + side * 110, sy],
        in: [[lane, -50], [lane, sy], [sx, sy]],
        out: [[sx, sy], [lane, sy], [lane, -50]],
        ramp: z.zone === 'CN' ? [[sx, sy], [lane, sy], [lane, z.y0 + 6]] : [[sx, sy], [lane, sy], [lane, quay + 30]],
      });
    }
    return {
      W, H, slots, quay, rampX: lane, cols: 7, zoom: 1.45, ship: {x: 34, y: quay + 30, w: 292, h: 48},
      zones: zones.map(z => ({zone: z.zone, title: [26, z.y0 + 15], stats: [W - 26, z.y0 + 15], scale: null})),
      cranes: [28, W - 28].map(x => ({x, y0: quay - 84, y1: quay + 72})), truck: null,
      paint(g) {
        g.innerHTML = `<image href="${ASSETS}/yard-narrow${PLATE}.webp?v=${V}" width="${W}" height="${H}" preserveAspectRatio="none"/>
          ${zones.map(z => `
            ${flag(z.zone, 26, z.y0 + 15)}<text x="53" y="${z.y0 + 15}" class="t-zone">${z.zone === 'KR' ? 'КОРЕЯ' : 'КИТАЙ'}</text>`).join('')}
          ${barrier(lane, 26, 'h')}`;
      },
    };
  }

  // флажок зоны перед названием (x, y — левый край и базовая линия текста)
  function flag(zone, x, y) {
    const w = 21, h = 14, t = y - 11;
    return zone === 'KR'
      ? `<g class="t-flag"><rect x="${x}" y="${t}" width="${w}" height="${h}" rx="1.5" fill="#fff"/>
          <path d="M${x + w / 2 - 4} ${t + h / 2} a4 4 0 0 1 8 0 Z" fill="#cd2e3a"/><path d="M${x + w / 2 - 4} ${t + h / 2} a4 4 0 0 0 8 0 Z" fill="#0047a0"/>
          <rect x="${x + 2}" y="${t + 2}" width="3" height="2" fill="#111"/><rect x="${x + w - 5}" y="${t + 2}" width="3" height="2" fill="#111"/>
          <rect x="${x + 2}" y="${t + h - 4}" width="3" height="2" fill="#111"/><rect x="${x + w - 5}" y="${t + h - 4}" width="3" height="2" fill="#111"/></g>`
      : `<g class="t-flag"><rect x="${x}" y="${t}" width="${w}" height="${h}" rx="1.5" fill="#de2910"/>
          <path d="${starPath(x + 5, t + 4.5, 3)}" fill="#ffde00"/>
          ${[[9.5, 2], [11, 4], [11, 6.5], [9.5, 8.5]].map(([dx, dy]) => `<circle cx="${x + dx}" cy="${t + dy}" r=".9" fill="#ffde00"/>`).join('')}</g>`;
  }
  function starPath(cx, cy, r) {
    return Array.from({length: 10}, (_, i) => {
      const a = -Math.PI / 2 + i * Math.PI / 5, rr = i % 2 ? r * 0.4 : r;
      return `${i ? 'L' : 'M'}${(cx + rr * Math.cos(a)).toFixed(2)} ${(cy + rr * Math.sin(a)).toFixed(2)}`;
    }).join('') + 'Z';
  }

  // шлагбаум у ворот (будка — на подложке): v — дорога горизонтальная, h — вертикальная
  function barrier(x, y, dir) {
    return dir === 'v'
      ? `<rect x="${x - 2}" y="${y - 22}" width="4" height="30" rx="2" fill="url(#t-barrier)" class="t-barrier"/>`
      : `<rect x="${x - 6}" y="${y - 2}" width="28" height="4" rx="2" fill="url(#t-barrier-h)" class="t-barrier t-barrier-h"/>`;
  }

  // --- машины сверху: спрайты из Blender (design/blender/port.py) ------------------------
  // Спрайт 6 × 3 м, нос вверх; 1 м = M единиц сцены. Цвет объявления → ближайшая краска из рендера.
  const M = 9, SPRITE = {w: 3 * M, h: 6 * M};
  const LENGTH = {sedan: 4.8, suv: 4.6, hatch: 3.9, van: 5.1};
  const WIDTH = {sedan: 1.86, suv: 1.92, hatch: 1.76, van: 1.98};
  const PAINTS = {white: '#eceef0', pearl: '#f2eee4', silver: '#c3c7cc', grey: '#8a9099', graphite: '#4b5058',
    black: '#1c1e22', blue: '#2f5fa6', red: '#c62a24'};
  function paintOf(hex) {
    const rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
    const c = rgb(hex || '#eceef0');
    let best = 'white', dist = Infinity;
    for (const [name, h] of Object.entries(PAINTS)) {
      const d = rgb(h).reduce((s, v, i) => s + (v - c[i]) ** 2, 0);
      if (d < dist) { dist = d; best = name; }
    }
    return best;
  }
  // спрайт из настоящей 3D-модели, если она есть для этой марки и модели; у трёх моделей — один родной цвет
  const SINGLE_PAINT = ['byd-seal', 'byd-song', 'geely-monjaro', 'hyundai-santafe24', 'chery-tiggo8'];
  function spriteOf(d, body) {
    if (d.model) return `${d.model}-${SINGLE_PAINT.includes(d.model) ? 'native' : paintOf(d.color)}`;
    return `${body}-${paintOf(d.color)}`;
  }
  function carShape(d) {
    const body = LENGTH[d.body] ? d.body : 'sedan';
    const l = LENGTH[body] * M, w = WIDTH[body] * M;
    return `
      <rect class="car-glow" x="${-w / 2 - 4}" y="${-l / 2 - 4}" width="${w + 8}" height="${l + 8}" rx="7"/>
      ${NIGHT ? `<path class="beam" d="M${-w / 2 + 2} ${-l / 2 + 1} L${-w / 2 - 10} ${-l / 2 - 46} L${w / 2 + 10} ${-l / 2 - 46} L${w / 2 - 2} ${-l / 2 + 1} Z" fill="url(#t-beam)"/>` : ''}
      <image href="${ASSETS}/cars/${spriteOf(d, body)}.webp?v=${V}" x="${-SPRITE.w / 2}" y="${-SPRITE.h / 2}" width="${SPRITE.w}" height="${SPRITE.h}"/>
      ${NIGHT ? `<g class="tail"><circle cx="${-w / 2 + 3}" cy="${l / 2 - 1}" r="3.4" fill="url(#t-tail)"/><circle cx="${w / 2 - 3}" cy="${l / 2 - 1}" r="3.4" fill="url(#t-tail)"/></g>` : ''}`;
  }

  // --- тестовые данные (?demo=1) ------------------------------------------------
  const DEMO = {
    KR: [['Kia K5', 'sedan'], ['Hyundai Sonata', 'sedan'], ['Kia Sportage', 'suv'], ['Hyundai Tucson', 'suv'],
      ['Kia Carnival', 'van'], ['Hyundai Avante', 'sedan'], ['Kia Seltos', 'suv'], ['Kia Ray', 'hatch'],
      ['Hyundai Santa Fe', 'suv'], ['Genesis G70', 'sedan'], ['Kia Sorento', 'suv'], ['Hyundai Staria', 'van']],
    CN: [['BYD Song Plus', 'suv'], ['Geely Monjaro', 'suv'], ['Changan UNI-K', 'suv'], ['Haval Jolion', 'suv'],
      ['Chery Tiggo 8', 'suv'], ['Geely Emgrand', 'sedan'], ['BYD Qin Plus', 'sedan'], ['Changan CS55', 'suv'],
      ['Toyota Camry', 'sedan'], ['Buick GL8', 'van'], ['Honda Fit', 'hatch'], ['Haval H6', 'suv']],
  };
  const DEMO_COLORS = ['#eceef0', '#eceef0', '#1c1e22', '#8a9099', '#c3c7cc', '#4b5058', '#2f5fa6', '#c62a24', '#f2eee4'];
  let demoSeq = 0;
  function demoCar(country) {
    const [title, body] = pick(DEMO[country]);
    const model = {'Hyundai Tucson': 'hyundai-tucson', 'Hyundai Santa Fe': 'hyundai-santafe24', 'Chery Tiggo 8': 'chery-tiggo8',
      'BYD Song Plus': 'byd-song', 'Geely Monjaro': 'geely-monjaro'}[title] || null;
    demoSeq += 1;
    const price = Math.round(rnd(1.2, 3.2) * 20) * 50000, year = 2019 + Math.floor(rnd(0, 5));
    const age = new Date().getFullYear() - year < 3 ? 'new' : 'mid', cc = pick([1598, 1598, 1999, 1497]);
    return {key: 'demo:' + demoSeq, source: 'demo', id: String(demoSeq), country, title, body, model, year,
      price: rub(price), photo: null, path: null, verdict: 'ok', color: pick(DEMO_COLORS), demo: true,
      turnkey: Math.round(price * rnd(1.22, 1.32) / 1000) * 1000 + 50000, turnkey_from: true,
      calc: {country, engine: 'ice', age, cc, price}};
  }

  // --- состояние сцены -----------------------------------------------------------
  let L, svg, gYard, gCars, gShip, gTags, gChips, gBoard, deck;
  const cars = new Map();        // key -> машина на сцене
  const queue = [];              // ждут заезда
  let occupied = [];             // место -> key
  let raf = 0, last = 0;
  let ship = {state: 'docked', x: 0, loaded: 0};
  const SPEED = 140;             // единиц сцены в секунду

  function build() {
    L = matchMedia('(max-width: 640px)').matches ? narrowLayout() : wideLayout();
    root.style.aspectRatio = `${L.W} / ${L.H}`;
    root.querySelector('svg')?.remove();
    svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${L.W} ${L.H}`);
    svg.setAttribute('class', 'terminal-svg');
    svg.innerHTML = `<defs>
      <pattern id="t-hazard" width="16" height="8" patternUnits="userSpaceOnUse" patternTransform="skewX(-45)">
        <rect width="16" height="8" fill="#e5b53a"/><rect width="8" height="8" fill="#1d1f23"/></pattern>
      <linearGradient id="t-barrier" x1="0" y1="0" x2="0" y2="1"><stop offset=".5" stop-color="#e0251f"/><stop offset=".5" stop-color="#fff"/></linearGradient>
      <linearGradient id="t-barrier-h" x1="0" y1="0" x2="1" y2="0"><stop offset=".5" stop-color="#e0251f"/><stop offset=".5" stop-color="#fff"/></linearGradient>
      <radialGradient id="t-wake"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
      <radialGradient id="t-dim-g" gradientUnits="userSpaceOnUse" cx="0" cy="0" r="${L.W * 0.3}">
        <stop offset=".25" stop-color="#05080c" stop-opacity="0"/><stop offset="1" stop-color="#05080c" stop-opacity=".62"/></radialGradient>
      <radialGradient id="t-cloud"><stop offset="0" stop-color="#000" stop-opacity=".22"/><stop offset=".6" stop-color="#000" stop-opacity=".12"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>
      <pattern id="t-glint" width="140" height="36" patternUnits="userSpaceOnUse">
        <ellipse cx="20" cy="8" rx="14" ry="1.2" fill="#fff"/><ellipse cx="88" cy="20" rx="20" ry="1.4" fill="#fff"/><ellipse cx="55" cy="31" rx="10" ry="1" fill="#fff"/></pattern>
      <clipPath id="t-water-clip"><rect y="${L.quay + 8}" width="${L.W}" height="${L.H - L.quay}"/></clipPath>
      <linearGradient id="t-beam" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#fff4d6" stop-opacity=".6"/><stop offset="1" stop-color="#fff4d6" stop-opacity="0"/></linearGradient>
      <radialGradient id="t-tail"><stop offset="0" stop-color="#ff2a1a" stop-opacity=".95"/><stop offset="1" stop-color="#ff2a1a" stop-opacity="0"/></radialGradient>
      <radialGradient id="t-nav-r"><stop offset="0" stop-color="#ff3b2f"/><stop offset="1" stop-color="#ff3b2f" stop-opacity="0"/></radialGradient>
      <radialGradient id="t-nav-g"><stop offset="0" stop-color="#39ff7a"/><stop offset="1" stop-color="#39ff7a" stop-opacity="0"/></radialGradient>
      <radialGradient id="t-nav-w"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
    </defs><g class="t-yard"></g>
    <g class="t-glints" clip-path="url(#t-water-clip)"><rect class="glint-band" x="${-L.W}" y="${L.quay}" width="${L.W * 3}" height="${L.H - L.quay}" fill="url(#t-glint)"/></g>
    <g class="t-ship"></g><g class="t-trucks"></g><rect class="t-dim" width="${L.W}" height="${L.H}" fill="url(#t-dim-g)"/>
    <g class="t-route-layer"></g><g class="t-chips"></g><g class="t-cars"></g><g class="t-board"></g><g class="t-cranes"></g><g class="t-clouds"></g><g class="t-tags"></g>`;
    if (NIGHT) svg.classList.add('night');
    root.prepend(svg);
    gYard = svg.querySelector('.t-yard');
    gCars = svg.querySelector('.t-cars');
    gShip = svg.querySelector('.t-ship');
    gTags = svg.querySelector('.t-tags');
    gChips = svg.querySelector('.t-chips');
    gBoard = svg.querySelector('.t-board');
    L.paint(gYard);
    const plate = gYard.querySelector('image');
    plate.addEventListener('load', () => svg.classList.add('ready'), {once: true});
    plate.addEventListener('error', () => {
      // ночной подложки нет — берём дневную
      if (PLATE) plate.setAttribute('href', plate.getAttribute('href').replace(PLATE + '.webp', '.webp'));
      plate.addEventListener('load', () => svg.classList.add('ready'), {once: true});
      if (!PLATE) svg.classList.add('ready');
    }, {once: true});
    if (!ship.loaded) ship.loaded = 3 + Math.floor(Math.random() * 5);
    paintShip();
    occupied = new Array(L.slots.length).fill(null);
    cam.vb = null; cam.car = null; cam.follow = null;
    ambient();
  }

  // --- живой фон: блики на воде, облака, тележки кранов, автовоз ------------------------
  function ambient() {
    const cranes = svg.querySelector('.t-cranes'), clouds = svg.querySelector('.t-clouds');
    cranes.innerHTML = L.cranes.map(c => `<g class="trolley"><rect x="${c.x - 12}" y="-6.5" width="24" height="13" rx="2"/><rect class="hoist" x="${c.x - 7}" y="-2.5" width="14" height="5"/></g>`).join('');
    if (!NIGHT) {
      clouds.innerHTML = [0.3, 0.75].map((y, i) => `<ellipse class="cloud" cx="0" cy="${L.H * y}" rx="${L.W * (0.2 + i * 0.06)}" ry="${L.H * (0.32 - i * 0.08)}" fill="url(#t-cloud)"/>`).join('');
    }
    if (reduce.matches) {
      cranes.querySelectorAll('.trolley').forEach((t, i) => t.setAttribute('transform', `translate(0 ${L.cranes[i].y0 + 40})`));
      return;
    }
    cranes.querySelectorAll('.trolley').forEach((t, i) => {
      const {y0, y1} = L.cranes[i];
      t.animate([{transform: `translateY(${y0}px)`, offset: 0}, {transform: `translateY(${y1}px)`, offset: 0.42},
        {transform: `translateY(${y1}px)`, offset: 0.55}, {transform: `translateY(${y0}px)`, offset: 0.95}, {transform: `translateY(${y0}px)`, offset: 1}],
      {duration: 17000 + i * 4300, iterations: Infinity, easing: 'ease-in-out', delay: -i * 6000});
    });
    clouds.querySelectorAll('.cloud').forEach((c, i) => {
      const rx = +c.getAttribute('rx');
      c.animate([{transform: `translateX(${-rx}px)`}, {transform: `translateX(${L.W + rx}px)`}],
        {duration: 70000 + i * 26000, iterations: Infinity, delay: -Math.random() * 60000});
    });
    svg.querySelector('.glint-band').animate([{transform: 'translateX(0)'}, {transform: 'translateX(140px)'}], {duration: 16000, iterations: Infinity});
  }
  function makeTruck(mine) {
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'truck');
    let load = '';
    for (let i = 0; i < 3; i++) {
      const d = i === 0 && mine ? mine : {body: pick(['sedan', 'suv', 'hatch']), color: pick(Object.values(PAINTS))};
      load += `<g class="${i === 0 && mine ? 'mine' : ''}" transform="translate(${-14 - i * 27} 0) rotate(90) scale(.78)"${i === 0 && !mine ? ' data-free opacity="0"' : ''}>${carShape(d)}</g>`;
    }
    g.innerHTML = `${NIGHT ? '<path class="beam on" d="M14 -8 L60 -16 L60 16 L14 8 Z" fill="url(#t-beam)" transform="rotate(0)"/>' : ''}
      <rect class="trailer" x="-86" y="-11" width="92" height="22" rx="2"/><rect class="rail" x="-84" y="-8.5" width="88" height="2"/><rect class="rail" x="-84" y="6.5" width="88" height="2"/>
      ${load}<rect class="cab" x="7" y="-10" width="17" height="20" rx="3"/><rect class="cab-glass" x="18" y="-8" width="4" height="16" rx="1"/>`;
    svg.querySelector('.t-trucks').appendChild(g);
    return g;
  }
  function truck() {  // проезжающий автовоз без остановки
    if (!L.truck || reduce.matches || document.hidden) return;
    const g = makeTruck(null);
    g.querySelector('[data-free]')?.setAttribute('opacity', '1');
    g.animate([{transform: `translate(-140px, ${L.truck}px)`}, {transform: `translate(${L.W + 140}px, ${L.truck}px)`}], {duration: 12000, easing: 'linear'})
      .onfinish = () => g.remove();
  }
  // Машина из Китая уезжает только автовозом: он подъезжает по дороге, машина заезжает на прицеп, автовоз уходит.
  // На телефоне автовоза нет — машина уезжает по проезду наверх, через ворота.
  function truckPickup(car, done) {
    const end = L.slots[car.slot].ramp.at(-1);
    const gone = () => { occupied[car.slot] = null; remove(car); done && done(); };
    if (!L.truck || reduce.matches) {
      drive(car, [end, [end[0], -60]], 'out', gone);
      return;
    }
    const g = makeTruck(null), stop = end[0] + 40, from = `translate(-140px, ${L.truck}px)`, at = `translate(${stop}px, ${L.truck}px)`;
    g.animate([{transform: from}, {transform: at}], {duration: 4200, easing: 'cubic-bezier(.2,.7,.3,1)', fill: 'forwards'}).onfinish = () => {
      drive(car, [end, [end[0], L.truck]], 'board', () => {
        car.g.classList.add('boarding');
        g.querySelector('[data-free]')?.remove();  // первое место на прицепе ждало эту машину
        const mine = document.createElementNS(NS, 'g');
        mine.setAttribute('class', 'mine');
        mine.setAttribute('transform', 'translate(-14 0) rotate(90) scale(.78)');
        mine.innerHTML = carShape(car.d);
        g.insertBefore(mine, g.querySelector('.cab'));
        setTimeout(gone, 400);
        g.animate([{transform: at}, {transform: `translate(${L.W + 140}px, ${L.truck}px)`}], {duration: 6000, easing: 'ease-in', delay: 500, fill: 'forwards'})
          .onfinish = () => g.remove();
      });
    };
  }

  // --- камера: приближение к выбранной машине ---------------------------------------------
  const cam = {vb: null, anim: 0, car: null, follow: null};
  const fullView = () => [0, 0, L.W, L.H];
  function setView(v) {
    cam.vb = v;
    svg.setAttribute('viewBox', v.map(n => n.toFixed(1)).join(' '));
    // при приближении ценники не раздуваются: держим их экранный размер
    const k = Math.max(0.72, Math.min(1, v[2] / L.W)).toFixed(3);
    if (gChips && k !== cam.chipK) { cam.chipK = k; gChips.style.setProperty('--chip-k', k); }
  }
  function zoomBox(car) {
    const f = L.zoom, w = L.W / f, h = L.H / f;
    const at = popEl.classList.contains('docked') ? 0.3 : 0.5;  // справа — карточка машины
    return [Math.max(0, Math.min(L.W - w, car.x - w * at)), Math.max(0, Math.min(L.H - h, car.y - h / 2)), w, h];
  }
  function flyTo(target, ms = 750) {
    cancelAnimationFrame(cam.anim);
    const from = (cam.vb || fullView()).slice(), t0 = performance.now();
    if (reduce.matches) ms = 0;
    const tick = t => {
      const k = ms ? Math.min(1, (t - t0) / ms) : 1, e = k < 0.5 ? 4 * k ** 3 : 1 - (-2 * k + 2) ** 3 / 2;
      setView(from.map((v, i) => v + (target[i] - v) * e));
      if (pop.car) position(pop.car);
      if (k < 1) cam.anim = requestAnimationFrame(tick);
    };
    cam.anim = requestAnimationFrame(tick);
  }
  function dimAt(car) {
    const g = svg.querySelector('#t-dim-g');
    g.setAttribute('cx', car.x.toFixed(1)); g.setAttribute('cy', car.y.toFixed(1));
  }
  function focusOn(car) {
    if (cam.car && cam.car !== car) cam.car.g.classList.remove('focus');
    cam.car = car;
    car.g.classList.add('focus');
    gCars.appendChild(car.g);  // поверх остальных
    gChips.querySelectorAll('.sel').forEach(c => c.classList.remove('sel'));
    if (car.chip) { car.chip.classList.add('sel'); gChips.appendChild(car.chip); }
    svg.classList.add('focused');
    dimAt(car);
    flyTo(zoomBox(car));
  }
  function unfocus() {
    if (!cam.car) return;
    cam.car.g.classList.remove('focus');
    cam.car.chip?.classList.remove('sel');
    cam.car = null; cam.follow = null;
    svg.classList.remove('focused');
    svg.querySelector('.t-route-layer').replaceChildren();
    flyTo(fullView());
  }
  // маршрут от места до рампы автовоза прорисовывается линией, потом по нему едет машина
  function drawRoute(car) {
    const pts = smooth(L.slots[car.slot].ramp);
    const path = document.createElementNS(NS, 'path');
    path.setAttribute('class', 't-route');
    path.setAttribute('d', 'M' + pts.map(p => p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' L'));
    svg.querySelector('.t-route-layer').replaceChildren(path);
    const len = path.getTotalLength();
    path.style.strokeDasharray = `${len}`;
    path.animate([{strokeDashoffset: len}, {strokeDashoffset: 0}], {duration: reduce.matches ? 0 : 900, easing: 'ease-out', fill: 'forwards'});
  }

  // Судно — рендер 560 × 92 (кадр 640 × 152, корпус с 50-й единицы); машины на палубе — те же спрайты.
  function paintShip() {
    const s = L.ship, k = s.w / 560;
    const rows = 3, cols = 8, pitchX = 47 * k, pitchY = 24 * k, car = 0.82 * k;
    deck = [];
    let marks = '';
    for (let c = 0; c < cols; c++) for (let r = 0; r < rows; r++) {
      const x = s.x + (92 + c * pitchX / k) * k, y = s.y + s.h / 2 + (r - 1) * pitchY;
      deck.push([x, y]);
      const d = {body: pick(['sedan', 'sedan', 'suv', 'suv', 'hatch', 'van']), color: pick(Object.values(PAINTS))};
      marks += `<g class="deck-car" transform="translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(90) scale(${car.toFixed(3)})" opacity="0">${carShape(d)}</g>`;
    }
    gShip.innerHTML = `<g class="ship-body">
      <ellipse class="ship-wake" cx="${s.x + 10 * k}" cy="${s.y + s.h / 2}" rx="${90 * k}" ry="${s.h * 0.7}" fill="url(#t-wake)"/>
      <g class="ship-bob">
        <image href="${ASSETS}/ship.webp?v=${V}" x="${s.x - 50 * k}" y="${s.y - 30 * k}" width="${640 * k}" height="${152 * k}"/>
        ${marks}
        <g class="ship-lights">
          <circle cx="${s.x + 470 * k}" cy="${s.y + 3}" r="${7 * k + 3}" fill="url(#t-nav-r)"/>
          <circle cx="${s.x + 470 * k}" cy="${s.y + s.h - 3}" r="${7 * k + 3}" fill="url(#t-nav-g)"/>
          <circle cx="${s.x + 40 * k}" cy="${s.y + s.h / 2}" r="${9 * k + 3}" fill="url(#t-nav-w)"/>
        </g>
      </g>
    </g>`;
    gShip.querySelector('.ship-body').style.transform = `translateX(${ship.x}px)`;
    gShip.querySelectorAll('.deck-car').forEach((el, i) => { if (i < ship.loaded) el.setAttribute('opacity', '1'); });
  }

  // --- машины --------------------------------------------------------------------
  // Диапазон цен под ключ по зонам (5–95 %), чтобы раскладывать машины по шкале
  const range = {KR: null, CN: null};
  function updateRange(list) {
    for (const zone of ['KR', 'CN']) {
      const prices = list.filter(d => (d.country === 'CN' ? 'CN' : 'KR') === zone && d.turnkey).map(d => d.turnkey).sort((a, b) => a - b);
      range[zone] = prices.length > 1 ? [prices[Math.floor(prices.length * 0.05)], prices[Math.ceil(prices.length * 0.95) - 1]] : null;
    }
  }
  function priceCol(d, zone) {
    const r = range[zone];
    if (!r || !d.turnkey || r[1] <= r[0]) return null;
    return Math.max(0, Math.min(1, (d.turnkey - r[0]) / (r[1] - r[0]))) * (L.cols - 1);
  }
  function freeSlot(zone, d) {
    const free = L.slots.map((s, i) => i).filter(i => L.slots[i].zone === zone && !occupied[i]);
    if (!free.length) return -1;
    const col = d && priceCol(d, zone);
    if (col === null || col === undefined) return pick(free);
    // ближайшее свободное место к «своей» колонке шкалы; среди равных — случайный ряд
    const best = Math.min(...free.map(i => Math.abs(L.slots[i].col - col)));
    return pick(free.filter(i => Math.abs(L.slots[i].col - col) <= best + 0.5));
  }
  function makeCar(d) {
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'car');
    g.innerHTML = carShape(d);
    g.addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') showPop(car, false); });
    g.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse' && !pop.pinned) hidePopSoon(); });
    g.addEventListener('click', () => { goal('car_click'); showPop(car, true); if (pop.car === car) focusOn(car); });
    g.addEventListener('dblclick', () => { if (car.d.path) openCard(car); });
    gCars.appendChild(g);
    const car = {d, g, slot: -1, state: 'new', path: null, dist: 0, len: 0, x: 0, y: 0, ang: 0, since: performance.now()};
    cars.set(d.key, car);
    return car;
  }
  function place(car, x, y, ang) {
    car.x = x; car.y = y; car.ang = ang;
    car.g.setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${ang.toFixed(1)})`);
  }
  function parkedAngle(slot) {
    // носом от проезда — как машина заехала на место
    const s = L.slots[slot], prev = s.in[s.in.length - 2];
    return Math.atan2(s.y - prev[1], s.x - prev[0]) * 180 / Math.PI + 90;
  }
  function smooth(path, r = 16) {
    const out = [path[0]];
    for (let i = 1; i < path.length - 1; i++) {
      const [ax, ay] = path[i - 1], [bx, by] = path[i], [cx, cy] = path[i + 1];
      const l1 = Math.hypot(bx - ax, by - ay), l2 = Math.hypot(cx - bx, cy - by);
      const rr = Math.min(r, l1 / 2, l2 / 2);
      if (!rr) { out.push(path[i]); continue; }
      const p = [bx - (bx - ax) / l1 * rr, by - (by - ay) / l1 * rr], q = [bx + (cx - bx) / l2 * rr, by + (cy - by) / l2 * rr];
      for (let t = 0; t <= 1.0001; t += 1 / 8) {  // квадратичная Безье p → b → q
        const u = 1 - t;
        out.push([u * u * p[0] + 2 * u * t * bx + t * t * q[0], u * u * p[1] + 2 * u * t * by + t * t * q[1]]);
      }
    }
    out.push(path[path.length - 1]);
    return out;
  }
  function drive(car, path, state, done) {
    path = smooth(path);
    let len = 0;
    for (let i = 1; i < path.length; i++) len += Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]);
    Object.assign(car, {path, len, dist: 0, state, done});
    car.g.classList.add('moving');
    if (reduce.matches) { finish(car); return; }
    car.g.style.opacity = '';
    kick();
  }
  function finish(car) {
    const p = car.path[car.path.length - 1];
    const done = car.done;
    car.path = null;
    car.g.classList.remove('moving');
    if (car.state === 'in') place(car, p[0], p[1], parkedAngle(car.slot));
    done && done();
  }
  function step(car, dt) {
    const edge = Math.min(car.dist, car.len - car.dist);
    car.dist = Math.min(car.len, car.dist + SPEED * dt * Math.max(0.25, Math.min(1, 0.35 + edge / 45)));
    let rest = car.dist, i = 1;
    for (; i < car.path.length; i++) {
      const seg = Math.hypot(car.path[i][0] - car.path[i - 1][0], car.path[i][1] - car.path[i - 1][1]);
      if (rest <= seg || i === car.path.length - 1) {
        const t = seg ? Math.min(1, rest / seg) : 1, a = car.path[i - 1], b = car.path[i];
        const target = Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI + 90;
        let delta = ((target - car.ang + 540) % 360) - 180;
        const ang = car.ang + delta * Math.min(1, dt * 14);
        place(car, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, ang);
        break;
      }
      rest -= seg;
    }
    if (car.dist >= car.len) finish(car);
  }

  function arrive(d, instant) {
    if (cars.has(d.key)) return;
    const zone = d.country === 'CN' ? 'CN' : 'KR';
    let slot = freeSlot(zone, d);
    if (slot < 0) {
      // мест нет — самая давняя машина зоны уезжает за ворота, новая встаёт на её место
      const oldest = [...cars.values()].filter(c => c.state === 'parked' && L.slots[c.slot].zone === zone)
        .sort((a, b) => a.since - b.since)[0];
      if (!oldest) { queue.push(d); return; }
      slot = oldest.slot;
      leave(oldest);
      occupied[slot] = d.key;
      setTimeout(() => enter(d, slot), reduce.matches ? 0 : 1600);
      return;
    }
    occupied[slot] = d.key;
    if (instant) {
      const car = makeCar(d);
      car.slot = slot; car.state = 'parked';
      place(car, L.slots[slot].x, L.slots[slot].y, parkedAngle(slot));
      chipOn(car);
      return;
    }
    enter(d, slot);
  }
  // ценник под ключ на асфальте у места: как табло цен
  const short = n => (n / 1e6).toFixed(2).replace('.', ',');
  function chipOn(car) {
    chipOff(car);
    const [x, y] = L.slots[car.slot].chip, t = car.d.turnkey;
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'chip' + (t ? '' : ' none'));
    g.setAttribute('transform', `translate(${x} ${y})`);
    g.innerHTML = `<g class="chip-in"><rect x="-19" y="-7.5" width="38" height="15" rx="7.5"/><text y="4" text-anchor="middle">${t ? short(t) : '—'}</text></g>`;
    gChips.appendChild(g);
    car.chip = g;
  }
  function chipOff(car) { car.chip?.remove(); car.chip = null; }

  function enter(d, slot) {
    if (!L.slots[slot] || occupied[slot] !== d.key) { queue.unshift(d); return; } // раскладка сменилась
    const car = makeCar(d);
    car.slot = slot;
    const p = L.slots[slot].in[0];
    place(car, p[0], p[1], 90);
    openGate();
    drive(car, L.slots[slot].in, 'in', () => {
      car.state = 'parked';
      car.since = performance.now();
      chipOn(car);
      tag(car, d);
      hud();
    });
    hud();
  }
  function leave(car) {
    chipOff(car);
    if (occupied[car.slot] === car.d.key) occupied[car.slot] = null;
    if (pop.car === car) hidePop();
    if (cam.car === car) { cam.follow = null; unfocus(); }
    drive(car, L.slots[car.slot].out, 'out', () => remove(car));
    openGate();
  }
  function remove(car) {
    chipOff(car);
    car.g.remove();
    cars.delete(car.d.key);
    if (occupied[car.slot] === car.d.key) occupied[car.slot] = null;
    hud();
  }
  function openGate() {
    const b = svg.querySelector('.t-barrier');
    if (!b || reduce.matches) return;
    b.classList.add('open');
    clearTimeout(openGate.t);
    openGate.t = setTimeout(() => b.classList.remove('open'), 1400);
  }

  // «Хочу эту»: машина подсвечивается и едет к рампе автовоза
  function toRamp(car, then) {
    if (car.state !== 'parked') return;
    chipOff(car);
    car.g.classList.add('chosen');
    drive(car, L.slots[car.slot].ramp, 'ramp', () => { car.state = 'at-ramp'; then && then(); });
  }
  function backToSlot(car) {
    car.g.classList.remove('chosen');
    drive(car, [...L.slots[car.slot].ramp].reverse(), 'back', () => {
      car.state = 'parked';
      place(car, L.slots[car.slot].x, L.slots[car.slot].y, parkedAngle(car.slot));
      chipOn(car);
    });
  }
  function depart(car) { if (car.d.country === 'CN') truckPickup(car); else load(car); }
  function load(car) {
    occupied[car.slot] = null;
    car.g.classList.add('boarding');
    setTimeout(() => remove(car), reduce.matches ? 0 : 500);
    ship.loaded = Math.min(deck.length, ship.loaded + 1);
    gShip.querySelectorAll('.deck-car')[ship.loaded - 1]?.setAttribute('opacity', '1');
  }

  // --- «Как она поедет ко мне»: выбранная машина грузится на судно (Корея) или автовоз (Китай),
  // транспорт уходит, полоса «Путь машины» под сценой идёт в такт. Потом машина снова встаёт на стоянку.
  let delivering = false;
  const routeAt = t => window.RenalRoute?.at(t);
  function deliver(car) {
    if (delivering || car.state !== 'parked') return;
    delivering = true;
    const d = car.d, byShip = d.country !== 'CN';
    hidePop();
    dispatchEvent(new CustomEvent('renal:car', {detail: {title: label(d), country: d.country === 'CN' ? 'cn' : 'kr', turnkey: d.turnkey, manual: true,
      sprite: `${ASSETS}/cars/${spriteOf(d, LENGTH[d.body] ? d.body : 'sedan')}.webp?v=${V}`}}));
    routeAt(0);
    cam.follow = car; focusOn(car);
    drawRoute(car);
    toast(`<b>${esc(label(d))}</b> — выкуплена и едет ${byShip ? 'на погрузку в порт' : 'к автовозу'}`);
    const done = () => {
      routeAt(1);
      toast(`<b>${esc(label(d))}</b> во Владивостоке: таможня, документы — и к вам. <a href="#" data-lead-open>Хочу так же →</a>`);
      setTimeout(() => { delivering = false; arrive(d, true); hud(); }, reduce.matches ? 0 : 1200);
    };
    const whenDocked = fn => (ship.state === 'docked' ? fn() : setTimeout(() => whenDocked(fn), 500));
    setTimeout(() => toRamp(car, () => whenDocked(() => {
      cam.follow = null; unfocus();
      if (byShip) {
        load(car);
        gShip.querySelectorAll('.deck-car')[ship.loaded - 1]?.classList.add('mine');
        routeAt(0.25);
        ship.state = 'leaving';
        setTimeout(() => {
          window.RenalRoute?.run(0.25, 0.75, 6000);
          moveShip(L.W + 40, 6, () => {
            ship.loaded = 0;
            ship.x = -L.ship.x - L.ship.w - 60;
            paintShip();
            done();
            moveShip(0, 7, () => { ship.state = 'docked'; });
          });
        }, reduce.matches ? 0 : 700);
      } else {
        routeAt(0.25);
        truckPickup(car, () => { window.RenalRoute?.run(0.25, 0.75, 6000); setTimeout(done, reduce.matches ? 0 : 6000); });
      }
    })), reduce.matches ? 0 : 500);
  }

  // --- судно: периодически уходит с машинами и приходит новое ------------------------
  function shipCycle() {
    if (delivering || reduce.matches || document.hidden || ship.state !== 'docked' || [...cars.values()].some(c => c.state === 'ramp' || c.state === 'at-ramp')) return;
    // перед отходом на борт заезжают 2–3 самые давние машины
    const old = [...cars.values()].filter(c => c.state === 'parked' && c.d.country !== 'CN').sort((a, b) => a.since - b.since).slice(0, 3);
    old.forEach((c, i) => setTimeout(() => toRamp(c, () => load(c)), i * 900));
    setTimeout(() => {
      if ([...cars.values()].some(c => c.state === 'ramp' || c.state === 'at-ramp')) return;
      ship.state = 'leaving';
      moveShip(L.W + 40, 7, () => {
        ship.loaded = 0;
        ship.x = -L.ship.x - L.ship.w - 60;
        paintShip();
        moveShip(0, 7, () => { ship.state = 'docked'; });
      });
    }, old.length * 900 + 4500);
  }
  function truckCycle() {
    if (delivering || reduce.matches || document.hidden) return;
    const c = [...cars.values()].filter(x => x.state === 'parked' && x.d.country === 'CN' && x !== cam.car).sort((a, b) => a.since - b.since)[0];
    if (!c || !L.truck) { truck(); return; }
    toRamp(c, () => truckPickup(c));
  }
  function moveShip(to, seconds, done) {
    const body = gShip.querySelector('.ship-body');
    body.style.transition = `transform ${seconds}s cubic-bezier(.45,.05,.4,1)`;
    body.classList.add('moving');
    setTimeout(() => body.classList.remove('moving'), seconds * 1000);
    requestAnimationFrame(() => { body.style.transform = `translateX(${to}px)`; });
    ship.x = to;
    setTimeout(() => { body.style.transition = ''; done(); }, seconds * 1000 + 50);
  }

  function frame(t) {
    const dt = Math.min(0.05, (t - last) / 1000 || 0);
    last = t;
    let moving = false;
    for (const car of cars.values()) if (car.path) { step(car, dt); moving = moving || !!car.path; }
    if (cam.follow && cam.vb) {
      const target = zoomBox(cam.follow), k = Math.min(1, dt * 3.5);
      setView(cam.vb.map((v, i) => v + (target[i] - v) * k));
      dimAt(cam.follow);
      if (cam.follow.path) moving = true;
    }
    raf = moving ? requestAnimationFrame(frame) : 0;
  }
  function kick() { if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); } }

  function tag(car, d) {
    const text = `${label(d)}${d.turnkey ? ' · ≈ ' + mln(d.turnkey) : d.price ? ' · ' + d.price + ' ₽' : ''}`;
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'arrival-tag');
    gTags.replaceChildren();  // одновременно — один ценник
    g.setAttribute('transform', `translate(${car.x.toFixed(1)} ${(car.y - 34).toFixed(1)})`);
    g.innerHTML = `<rect rx="7" height="22" y="-11"/><path d="M-5 11 L0 17 L5 11 Z"/><text y="4" text-anchor="middle">${esc(text)}</text>
      <text class="tag-sub" y="-16" text-anchor="middle">новое объявление</text>`;
    gTags.appendChild(g);
    const t = g.querySelector('text'), w = t.getComputedTextLength() + 18;
    const r = g.querySelector('rect');
    r.setAttribute('x', -w / 2); r.setAttribute('width', w);
    // не вылезать за край сцены
    const shift = Math.max(0, w / 2 + 6 - car.x) - Math.max(0, car.x + w / 2 + 6 - L.W);
    if (shift) [t, r, g.querySelector('.tag-sub')].forEach(el => el.setAttribute('transform', `translate(${shift} 0)`));
    setTimeout(() => g.classList.add('out'), 3200);
    setTimeout(() => g.remove(), 3800);
  }

  // --- HUD и плашки ------------------------------------------------------------------
  const toasts = root.querySelector('.terminal-toasts');
  async function share({title, text, url}) {
    goal('share');
    if (navigator.share) { try { await navigator.share({title, text, url}); } catch (err) { /* отменили */ } return; }
    try { await navigator.clipboard.writeText(url); } catch (err) { /* без доступа к буферу — ссылка видна в тосте */ }
    toast(`Ссылка скопирована — отправьте её в MAX или <a href="https://vk.com/share.php?url=${encodeURIComponent(url)}" target="_blank" rel="noopener">ВКонтакте →</a>`);
  }
  window.RenalShare = share;
  function toast(html) {
    const el = document.createElement('div');
    el.className = 'terminal-toast';
    el.innerHTML = html;
    toasts.prepend(el);
    while (toasts.children.length > 2) toasts.lastElementChild.remove();
    setTimeout(() => el.classList.add('out'), 3800);
    setTimeout(() => el.remove(), 4300);
  }
  function board() {
    if (!gBoard) return;
    const word = n => n % 10 === 1 && n % 100 !== 11 ? 'машина' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'машины' : 'машин';
    gBoard.innerHTML = L.zones.map(z => {
      const here = [...cars.values()].filter(c => c.state !== 'out' && (c.d.country === 'CN' ? 'CN' : 'KR') === z.zone);
      const prices = here.map(c => c.d.turnkey).filter(Boolean);
      const stats = `${here.length} ${word(here.length)}${prices.length ? ' · от ' + mln(Math.min(...prices)) : ''}`;
      let scale = '';
      const r = range[z.zone];
      if (z.scale && r) {
        const {x0, x1, y} = z.scale, mid = (r[0] + r[1]) / 2;
        scale = `<g class="t-scale"><line x1="${x0}" x2="${x1}" y1="${y}" y2="${y}"/>
          ${[[x0, r[0], 'start'], [(x0 + x1) / 2, mid, 'middle'], [x1, r[1], 'end']].map(([x, v, a]) =>
            `<line x1="${x}" x2="${x}" y1="${y - 4}" y2="${y + 4}"/><text x="${x}" y="${y + 16}" text-anchor="${a}">${short(v)} млн</text>`).join('')}
          <text class="t-scale-cap" x="${(x0 + x1) / 2}" y="${y - 9}" text-anchor="middle">← дешевле · дороже →</text></g>`;
      }
      return `<text class="t-zone-sub t-stats" x="${z.stats[0]}" y="${z.stats[1]}" text-anchor="end">${stats}</text>${scale}`;
    }).join('');
  }
  function hud() {
    board();
    const list = [...cars.values()].filter(c => c.state !== 'out');
    const kr = list.filter(c => c.d.country !== 'CN').length;
    // на десктопе — курс, по которому посчитаны цены под ключ (сводка по зонам — на табло)
    const r = DATA.rates || {}, f = (v, d) => v.toLocaleString('ru-RU', {minimumFractionDigits: d, maximumFractionDigits: d});
    const rates = [r.CNY && `¥1 = ${f(r.CNY, 2)} ₽`, r.KRW && `₩1000 = ${f(r.KRW * 1000, 1)} ₽`, r.EUR && `€1 = ${f(r.EUR, 1)} ₽`].filter(Boolean);
    root.querySelector('[data-hud="count"]').textContent = L.W < 600
      ? `${list.length} машин · KR ${kr} · CN ${list.length - kr}`
      : rates.length && !matchMedia('(min-width: 1241px)').matches ? `${DATA.rates_source === 'ЦБ РФ' ? 'Курс ЦБ' : 'Курс'}: ${rates.join(' · ')}`  // на планшете в шапке курса нет
      : `${list.length} ${list.length % 10 === 1 && list.length % 100 !== 11 ? 'машина' : [2, 3, 4].includes(list.length % 10) && ![12, 13, 14].includes(list.length % 100) ? 'машины' : 'машин'} на стоянке`;  // курс — в шапке сайта
  }
  function setStatus(on, text) {
    root.querySelector('.hud-live .dot').classList.toggle('on', on);
    root.querySelector('[data-hud="status"]').textContent = text;
  }

  // --- мини-карточка ----------------------------------------------------------------
  const popEl = document.getElementById('port-pop');
  const stage = popEl.parentElement;
  const pop = {car: null, pinned: false, t: 0};
  popEl.addEventListener('pointerenter', () => clearTimeout(pop.t));
  popEl.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse' && !pop.pinned) hidePopSoon(); });
  document.addEventListener('pointerdown', e => {
    if (pop.car && !popEl.contains(e.target) && !pop.car.g.contains(e.target)) hidePop();
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') hidePop(); });

  function showPop(car, pinned) {
    clearTimeout(pop.t);
    if (car.state !== 'parked') return;
    if (pop.car && pop.car !== car) pop.car.g.classList.remove('hover');
    pop.car = car;
    pop.pinned = pinned || pop.pinned;
    // по нажатию карточка не висит над машиной: на компьютере — у правого края сцены, на телефоне — снизу экрана
    const wide = matchMedia('(min-width: 900px)').matches;
    popEl.classList.toggle('docked', pop.pinned && wide);
    popEl.classList.toggle('sheet', pop.pinned && !wide);
    document.body.classList.toggle('pop-sheet', pop.pinned && !wide);
    car.g.classList.add('hover');
    const d = car.d;
    // выбранная машина «едет» дальше по странице — в блоке логистики
    if (pinned) dispatchEvent(new CustomEvent('renal:car', {detail: {title: label(d), country: d.country === 'CN' ? 'cn' : 'kr', turnkey: d.turnkey,
      sprite: `${ASSETS}/cars/${spriteOf(d, LENGTH[d.body] ? d.body : 'sedan')}.webp?v=${V}`}}));
    // карточка: фото, название, главное о машине и два действия — расчёт у менеджера и страница машины
    const facts = [d.year, d.mileage && `${d.mileage} км`, d.cc && `${(d.cc / 1000).toFixed(1).replace('.', ',')} л`,
      d.fuel && d.fuel.toLowerCase()].filter(Boolean).join(' · ');
    const price = d.turnkey
      ? `<div class="pop-price">≈ ${mln(d.turnkey)}</div><div class="pop-orig">во Владивостоке с растаможкой, ориентировочно</div>`
      : d.price ? `<div class="pop-price">≈ ${esc(d.price)} ₽</div><div class="pop-orig">цена на площадке, без доставки и растаможки</div>` : '';
    popEl.innerHTML = `
      <button class="pop-x" type="button" data-act="close" aria-label="Закрыть">×</button>
      ${d.photo ? `<div class="pop-ph"><img src="${esc(d.photo)}" alt=""></div>` : ''}
      ${d.demo ? '<div class="pop-demo">Тестовые данные</div>' : ''}
      <div class="pop-body">
        <b class="pop-title">${esc(d.title)}</b>
        ${facts ? `<div class="pop-facts">${esc(String(facts))}</div>` : ''}
        ${price}
        <div class="pop-actions">
          <button class="btn" type="button" data-act="want">Рассчитать стоимость</button>
          ${d.path ? `<a class="btn ghost" href="${esc(d.path)}" data-act="more">Подробнее о машине →</a>` : ''}
        </div>
        <div class="pop-row"><p class="pop-note">Менеджер посчитает доставку, таможню и оформление до вашего города</p>
          <button type="button" class="pop-share" data-act="share" aria-label="Поделиться машиной"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 3v12M7 8l5-5 5 5M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button></div>
      </div>`;
    popEl.querySelector('[data-act="close"]').addEventListener('click', () => { cam.follow = null; hidePop(); });
    popEl.querySelector('[data-act="share"]').addEventListener('click', () => {
      const url = new URL(d.path || location.pathname, location.origin).href;
      share({title: label(d), url, text: `${label(d)}${d.turnkey ? ` — ≈ ${mln(d.turnkey)} с растаможкой во Владивостоке` : ''}. Нашёл в живой подборке Ренал Авто`});
    });
    popEl.querySelector('[data-act="more"]')?.addEventListener('click', e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;  // в новой вкладке — как обычная ссылка
      e.preventDefault();
      openCard(car);
    });
    popEl.querySelector('[data-act="want"]').addEventListener('click', () => {
      cam.follow = car;
      if (cam.car !== car) focusOn(car);
      hidePop();
      goal('car_want');
      let opened = false;
      const open = () => { if (!opened) { opened = true; openForm(d, car); } };
      drawRoute(car);
      setTimeout(() => toRamp(car, open), reduce.matches ? 0 : 500);
      setTimeout(open, 2600);
    });
    popEl.hidden = false;
    position(car);
  }
  function position(car) {
    const r = car.g.getBoundingClientRect(), s = stage.getBoundingClientRect();
    const w = popEl.offsetWidth, h = popEl.offsetHeight;
    if (popEl.classList.contains('sheet')) { popEl.style.left = popEl.style.top = ''; return; }
    if (popEl.classList.contains('docked')) {  // у правого края сцены, сцену не перекрывает снаружи
      const t = root.getBoundingClientRect();
      popEl.style.left = (t.right - s.left - w - 16) + 'px';
      popEl.style.top = (t.top - s.top + Math.max(16, (t.height - h) / 2)) + 'px';
      return;
    }
    let left = r.left + r.width / 2 - s.left - w / 2;
    left = Math.max(4, Math.min(s.width - w - 4, left));
    let top = r.top - s.top - h - 10;
    if (top < 4) top = r.bottom - s.top + 10;
    popEl.style.left = left + 'px';
    popEl.style.top = top + 'px';
  }
  function hidePopSoon() { clearTimeout(pop.t); pop.t = setTimeout(() => { if (!pop.pinned) hidePop(); }, 260); }
  function hidePop() {
    clearTimeout(pop.t);
    pop.car?.g.classList.remove('hover');
    pop.car = null; pop.pinned = false;
    popEl.hidden = true;
    popEl.classList.remove('docked', 'sheet');
    document.body.classList.remove('pop-sheet');
    if (!cam.follow) unfocus();
  }

  // --- переход к карточке машины: фото «вылетает» из сцены на весь экран, потом открывается страница
  function openCard(car) {
    const d = car.d;
    if (!d.path) return;
    goal('car_open');
    if (reduce.matches) { location.href = d.path; return; }
    const src = popEl.hidden ? null : popEl.querySelector('.pop-ph img');
    const from = (src || car.g).getBoundingClientRect();
    hidePop();
    const fly = document.createElement('div');
    fly.className = 'car-fly';
    const sprite = `${ASSETS}/cars/${spriteOf(d, LENGTH[d.body] ? d.body : 'sedan')}.webp?v=${V}`;
    fly.innerHTML = `<div class="car-fly-bg"></div><div class="car-fly-card">
      <img class="${d.photo ? '' : 'sprite'}" src="${esc(d.photo || sprite)}" alt="">
      <div class="car-fly-info"><b>${esc(label(d))}</b>${d.turnkey ? `<span>≈ ${mln(d.turnkey)} с растаможкой</span>` : ''}</div></div>`;
    document.body.appendChild(fly);
    const card = fly.querySelector('.car-fly-card');
    const w = Math.min(innerWidth - 32, 980), h = Math.min(innerHeight - 96, w * 0.66);
    const to = {left: (innerWidth - w) / 2, top: (innerHeight - h) / 2, width: w, height: h};
    const px = r => ({left: r.left + 'px', top: r.top + 'px', width: r.width + 'px', height: r.height + 'px'});
    card.animate([{...px(from), borderRadius: '8px', opacity: 0.6}, {...px(to), borderRadius: '20px', opacity: 1}],
      {duration: 560, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'forwards'});
    fly.querySelector('.car-fly-bg').animate([{opacity: 0}, {opacity: 1}], {duration: 420, fill: 'forwards'});
    // браузеры с переходами между страницами «доводят» фото до места на странице машины
    if (d.photo) fly.querySelector('img').style.viewTransitionName = 'car-photo';
    try { sessionStorage.setItem('car-fly', '1'); } catch (err) { /* приватный режим */ }
    setTimeout(() => { location.href = d.path; }, 600);
  }
  // вернулись «назад» из карточки — убираем заставку
  addEventListener('pageshow', () => document.querySelectorAll('.car-fly').forEach(el => el.remove()));

  // --- форма заявки с подставленной машиной ---------------------------------------------
  const dialog = document.getElementById('car-dialog');
  const form = dialog.querySelector('form');
  const blank = form.innerHTML;
  let formCar = null, sent = false;
  // заявка без конкретной машины: «Подобрать под бюджет», «Получить точный расчёт», «Хочу так же»
  function openLead({title = 'Подобрать под бюджет', note = 'Подберём оптимальные варианты в Корее и Китае и посчитаем, во сколько обойдётся каждый.', comment = ''} = {}) {
    goal('form_open');
    if (!form.querySelector('[name="name"]')) form.innerHTML = blank;
    form.querySelector('#car-dialog-title').textContent = title;
    form.querySelector('[data-cd-car]').hidden = true;
    form.querySelector('[data-car-name]').textContent = note;
    form.querySelector('[name="source"]').value = '';
    form.querySelector('[name="external_id"]').value = '';
    form.querySelector('[name="comment"]').value = comment;
    formCar = null;
    sent = false;
    dialog.showModal();
  }
  window.RenalLead = {open: openLead};
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-lead-open]');
    if (b) { e.preventDefault(); openLead(); }
  });
  function openForm(d, car) {
    goal('form_open');
    if (!form.querySelector('[name="name"]')) form.innerHTML = blank; // после прошлой отправки
    // в шапке формы — та самая машина: фото (или вид сверху), название, ориентир по цене
    const box = form.querySelector('[data-cd-car]'), thumb = form.querySelector('[data-cd-thumb]');
    thumb.src = d.photo || `${ASSETS}/cars/${spriteOf(d, LENGTH[d.body] ? d.body : 'sedan')}.webp?v=${V}`;
    thumb.classList.toggle('sprite', !d.photo);
    form.querySelector('[data-cd-title]').textContent = label(d);
    form.querySelector('[data-cd-price]').textContent = d.turnkey ? `≈ ${mln(d.turnkey)} с растаможкой`
      : d.price ? `≈ ${d.price} ₽ на площадке` : '';
    box.hidden = false;
    form.querySelector('[data-car-name]').textContent = '';
    form.querySelector('[name="source"]').value = d.demo ? '' : d.source;
    form.querySelector('[name="external_id"]').value = d.demo ? '' : d.id;
    form.querySelector('#car-dialog-title').textContent = 'Рассчитать стоимость';
    form.querySelector('[name="comment"]').value = '';
    formCar = car || null;
    sent = false;
    dialog.showModal();
  }
  form.addEventListener('click', e => { if (e.target.closest('[data-close]')) dialog.close(); });
  dialog.addEventListener('click', e => { if (e.target === dialog) dialog.close(); });
  form.addEventListener('lead:sent', () => {
    sent = true;
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'btn ghost block'; close.dataset.close = ''; close.textContent = 'Вернуться к машинам';
    form.appendChild(close);
  });
  dialog.addEventListener('close', () => {
    const car = formCar;
    formCar = null;
    if (!car || !cars.has(car.d.key)) { cam.follow = null; unfocus(); return; }
    if (sent) { depart(car); toast('Заявка принята · менеджер посчитает итоговую цену'); }
    else if (car.state === 'at-ramp') backToSlot(car);
    else car.g.classList.remove('chosen');
    cam.follow = null;
    unfocus();
  });

  // --- данные: стартовый набор, затем живая лента (или тестовый поток) -------------------
  // --- пульт подбора: под фильтр машины уезжают и заезжают ------------------------------
  const filterForm = document.querySelector('form[data-port-filter]');
  const filterOut = filterForm?.querySelector('[data-pf-result]');
  let filter = {}, filterSeq = 0, demoPool = [];
  const filterActive = () => Object.values(filter).some(Boolean);
  function matches(d, f = filter) {
    if (f.country && d.country !== filter.country) return false;
    if (f.body && d.body !== f.body) return false;
    if (f.year_from && !(d.year && d.year >= +f.year_from)) return false;
    if (f.budget && !(d.turnkey && d.turnkey <= +f.budget)) return false;
    if (f.q && !d.title.toLowerCase().includes(f.q.toLowerCase())) return false;
    return true;
  }
  function resultText(n, total) {
    if (!filterActive()) return '';
    if (!n) return 'Под этот запрос машин сейчас нет — <a href="#" data-pf-lead>оставьте заявку</a>, пришлём, как только появятся.<span data-pf-near></span>';
    const word = total % 10 === 1 && total % 100 !== 11 ? 'машина' : [2, 3, 4].includes(total % 10) && ![12, 13, 14].includes(total % 100) ? 'машины' : 'машин';
    return `Под ваш запрос — <b>${total} ${word}</b>.`;
  }
  async function search(f) {
    if (DATA.demo) { const found = demoPool.filter(d => matches(d, f)); return {found, total: found.length}; }
    const res = await fetch('/api/port/cars?' + new URLSearchParams(f));
    const body = await res.json();
    return {found: body.cars, total: body.total};
  }
  // ничего не нашлось — предлагаем, что ослабить: бюджет, год или марку, и сколько тогда будет машин
  const RELAX = [['budget', 'поднять бюджет'], ['year_from', 'взять постарше']];  // марку не трогаем: её человек выбрал сам
  async function suggestNear(my) {
    const f = {...filter}, dropped = [], texts = [];
    for (const [key, text] of RELAX) {  // ослабляем по очереди, пока не найдутся машины
      if (!f[key]) continue;
      delete f[key]; dropped.push(key); texts.push(text);
      let r;
      try { r = await search(f); } catch (err) { return; }
      if (my !== filterSeq) return;
      if (r.total) {
        const box = filterOut.querySelector('[data-pf-near]');
        if (box) box.innerHTML = ` <button type="button" class="pf-near" data-pf-relax="${dropped.join(',')}">Показать ${r.total} ${carWord(r.total)}, если ${texts.join(' и ')} →</button>`;
        return;
      }
    }
  }
  function carWord(n) {
    return n % 10 === 1 && n % 100 !== 11 ? 'машину' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'машины' : 'машин';
  }
  async function applyFilter() {
    filter = Object.fromEntries([...new FormData(filterForm)].filter(([, v]) => v !== ''));
    const my = ++filterSeq;
    let r;
    try { r = await search(filter); } catch (err) { return; }
    if (my !== filterSeq) return;
    goal('filter');
    filterOut.innerHTML = resultText(r.found.length, r.total);
    const qs = new URLSearchParams(filter);
    for (const k of ['demo', 'utm_source', 'utm_medium', 'utm_campaign']) { const v = new URLSearchParams(location.search).get(k); if (v) qs.set(k, v); }
    history.replaceState(null, '', location.pathname + (qs.toString() ? '?' + qs : '') + location.hash);
    if (r.found.length && filterActive()) {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'pf-share'; b.textContent = 'Поделиться подборкой';
      b.addEventListener('click', () => share({title: document.title, text: `${lotName()}: ${r.total} ${carWord(r.total).replace('машину', 'машина')} в живой подборке Ренал Авто`, url: location.href}));
      filterOut.append(' ', b);
    }
    switchLot(r.found, lotName());
    if (!r.found.length && filterActive()) suggestNear(my);
  }

  // Смена фильтра — «перелёт» на другую стоянку: сцена уезжает в сторону, приезжает новая,
  // уже заполненная подходящими машинами. Новые объявления из ленты по-прежнему заезжают через ворота.
  // бюджет — ползунок: крайнее правое положение — «любой»
  const budgetRange = filterForm?.querySelector('[data-pf-budget]');
  const budgetText = v => `до ${(v / 1e6).toLocaleString('ru-RU', {maximumFractionDigits: 2})} млн ₽`;
  budgetRange?.addEventListener('input', () => {
    const any = +budgetRange.value >= +budgetRange.max, text = any ? 'любой' : budgetText(+budgetRange.value);
    filterForm.elements.budget.value = any ? '' : budgetRange.value;
    filterForm.querySelector('[data-pf-budget-out]').textContent = text;
    budgetRange.setAttribute('aria-valuetext', text);
    budgetRange.style.setProperty('--fill', `${(budgetRange.value - budgetRange.min) / (budgetRange.max - budgetRange.min) * 100}%`);
  });
  filterForm?.querySelectorAll('[data-pf-quick]').forEach(b => b.addEventListener('click', () => {
    budgetRange.value = b.dataset.pfQuick;
    budgetRange.dispatchEvent(new Event('input', {bubbles: true}));
  }));
  function syncQuick() {
    filterForm?.querySelectorAll('[data-pf-quick]').forEach(b => b.classList.toggle('on', +b.dataset.pfQuick === +budgetRange.value));
  }
  budgetRange?.addEventListener('input', syncQuick);
  if (budgetRange) syncQuick();
  function lotName() {
    const f = filterForm.elements, parts = [];
    if (f.q.value.trim()) parts.push(f.q.value.trim());
    if (f.year_from.selectedIndex) parts.push(f.year_from.selectedOptions[0].text + ' г.');
    if (f.country.selectedIndex) parts.push(f.country.selectedOptions[0].text);
    if (f.budget.value) parts.push(budgetText(+f.budget.value));
    return parts.length ? parts.join(' · ') : 'Все объявления';
  }
  let switching = 0;
  function switchLot(found, name) {
    const my = ++switching;
    hidePop(); cam.follow = null; unfocus();
    const restock = () => {
      for (const c of [...cars.values()]) remove(c);
      occupied.fill(null);
      queue.length = 0;
      const byZone = {KR: 0, CN: 0}, cap = L.slots.length / 2;
      for (const d of found) {
        const z = d.country === 'CN' ? 'CN' : 'KR';
        if (byZone[z] < cap) { byZone[z]++; arrive(d, true); } else queue.push(d);
      }
      hud();
    };
    if (reduce.matches || !svg.classList.contains('ready')) { restock(); return; }
    const sign = root.querySelector('.lot-sign');
    sign.textContent = name;
    root.classList.add('lot-out');
    setTimeout(() => {
      if (my !== switching) return;
      restock();
      root.classList.remove('lot-out');
      root.classList.add('lot-in');
      requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('lot-in')));
      setTimeout(() => { if (my === switching) sign.classList.add('show'); }, 60);
      setTimeout(() => { if (my === switching) sign.classList.remove('show'); }, 1800);
    }, 320);
  }
  filterForm?.addEventListener('input', () => { clearTimeout(applyFilter.t); applyFilter.t = setTimeout(applyFilter, 350); });
  filterForm?.addEventListener('submit', e => e.preventDefault());
  // на телефоне фильтр свёрнут в одну строку, чтобы стоянка была видна сразу
  filterForm?.querySelector('[data-pf-toggle]')?.addEventListener('click', e => {
    const open = filterForm.classList.toggle('open');
    e.currentTarget.setAttribute('aria-expanded', String(open));
  });
  filterOut?.addEventListener('click', e => {
    const relax = e.target.closest('[data-pf-relax]');
    if (relax) {  // сбросить мешающий фильтр и показать машины
      const f = filterForm.elements;
      for (const k of relax.dataset.pfRelax.split(',')) {
        if (k === 'budget') budgetRange.value = budgetRange.max;
        else f[k].value = '';
      }
      budgetRange.dispatchEvent(new Event('input', {bubbles: true}));
      return;
    }
    if (!e.target.closest('[data-pf-lead]')) return;
    e.preventDefault();
    const f = filterForm.elements;
    const parts = [f.q.value, f.year_from.selectedIndex ? f.year_from.selectedOptions[0].text + ' г.' : '', f.country.selectedIndex ? 'из ' + f.country.selectedOptions[0].text : '',
      f.budget.value ? 'бюджет ' + budgetText(+f.budget.value) : ''].filter(Boolean);
    openLead({title: 'Сообщим, когда появится', note: 'Под этот запрос машин сейчас нет — менеджер напишет, когда найдёт.',
      comment: 'Ищу: ' + parts.join(', ') + '. Сообщите, когда появится.'});
  });

  // машины заезжают по одной; под фильтр — быстрее
  function feed() {
    clearTimeout(feed.t);
    let delay = 4200;
    if (!document.hidden) {
      if (queue.length) { arrive(queue.shift()); delay = filterActive() ? 650 : 4200; }
      else if (DATA.demo && !filterActive()) arrive(demoCar(Math.random() < 0.5 ? 'KR' : 'CN'));
    }
    if (!reduce.matches) feed.t = setTimeout(feed, delay);
  }
  function connect() {
    if (DATA.demo) { setStatus(true, 'Тестовые данные'); return; }
    if (!window.EventSource) { setStatus(false, 'Объявления'); return; }
    const es = new EventSource('/api/stream');
    es.onopen = () => setStatus(true, 'Живая лента');
    es.onerror = () => setStatus(false, 'Переподключаемся…');
    es.addEventListener('new', async e => {
      const l = JSON.parse(e.data).listing;
      const res = await fetch(`/api/port/${encodeURIComponent(l.source)}/${encodeURIComponent(l.external_id)}`);
      if (res.status !== 200) return;
      const d = await res.json();
      if (matches(d)) queue.unshift(d);
    });
  }

  function init() {
    build();
    let start = DATA.cars.slice();
    if (DATA.demo) {
      for (let i = 0; i < 200; i++) demoPool.push(demoCar(i % 2 ? 'CN' : 'KR'));
      if (start.length < 80) start.push(...demoPool.slice(0, 90 - start.length));
    }
    // машины из рекламной ссылки (?model=…) заезжают первыми, на глазах у посетителя
    const matched = DATA.match ? start.filter(d => d.title.toLowerCase().includes(DATA.match.toLowerCase())) : [];
    const rest = start.filter(d => !matched.includes(d));
    updateRange([...start, ...demoPool]);
    const parkNow = Math.round(L.slots.length * 0.6);
    rest.slice(0, parkNow).forEach(d => arrive(d, true));
    queue.push(...matched.slice(0, 4), ...rest.slice(parkNow), ...matched.slice(4));
    hud();
    connect();
    if (!reduce.matches) {
      feed.t = setTimeout(feed, 900);
      setInterval(shipCycle, 42000);
      setTimeout(truck, 6000);
      setInterval(truckCycle, 26000);
    } else {
      queue.splice(0).forEach(d => arrive(d, true));
    }
    if (filterForm) {  // ссылка с подборкой (?budget=…&year_from=…) или ?model=… из рекламы — сразу как фильтр
      const u = new URLSearchParams(location.search), f = filterForm.elements;
      if (u.get('budget')) { budgetRange.value = u.get('budget'); budgetRange.dispatchEvent(new Event('input')); }
      for (const k of ['country', 'year_from', 'q']) if (u.get(k) && f[k]) f[k].value = u.get(k);
      if (['budget', 'country', 'year_from', 'q'].some(k => u.get(k)) || f.q.value) { filterForm.classList.add('open'); applyFilter(); }
    }
    let wide = !matchMedia('(max-width: 640px)').matches;
    addEventListener('resize', () => {
      if (pop.car) position(pop.car);
      const now = !matchMedia('(max-width: 640px)').matches;
      if (now === wide) return;
      wide = now;
      // другая раскладка: заново расставляем машины, которые стоят на терминале
      const keep = [...cars.values()].filter(c => c.state === 'parked').map(c => c.d);
      hidePop();
      cars.clear();
      ship = {state: 'docked', x: 0, loaded: 0};
      build();
      keep.forEach(d => arrive(d, true));
      hud();
    });
  }

  const go = () => ('requestIdleCallback' in window ? requestIdleCallback(init, {timeout: 1200}) : setTimeout(init, 200));
  if (document.readyState === 'complete') go(); else addEventListener('load', go);
})();
