// Сцена «Порт» на лендинге: объявления из живой ленты — машины, которые заезжают на терминал.
// Сцена декоративная (aria-hidden) и стартует после загрузки страницы: без неё лендинг работает полностью.
(() => {
  const root = document.getElementById('terminal');
  const dataEl = document.getElementById('port-data');
  if (!root || !dataEl) return;
  const NS = 'http://www.w3.org/2000/svg';
  const DATA = JSON.parse(dataEl.textContent);
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const goal = name => { if (window.ym && window.YM_ID) window.ym(window.YM_ID, 'reachGoal', name); };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const rnd = (a, b) => a + Math.random() * (b - a);
  const pick = arr => arr[Math.floor(Math.random() * arr.length)];
  const label = d => `${d.title}${d.year ? ' ' + d.year : ''}`;

  document.querySelectorAll('[data-goal]').forEach(a => a.addEventListener('click', () => goal(a.dataset.goal)));

  // --- раскладка терминала ----------------------------------------------------
  // Две раскладки: широкая (десктоп) и узкая вертикальная полоса в 2 ряда (телефон), судно внизу.
  // Каждое место: где стоит машина и три маршрута — заезд через ворота, выезд обратно и путь к рампе.
  function wideLayout() {
    const W = 1200, H = 560, road = 56, aisle = 210, apron = 362, quay = 420, rampX = 600;
    const zones = [{zone: 'KR', x0: 40}, {zone: 'CN', x0: 620}];
    const slots = [];
    for (const z of zones) {
      const cx = z.x0 + 24;
      for (const sy of [160, 262]) for (let i = 0; i < 10; i++) {
        const sx = z.x0 + 76 + i * 50;
        slots.push({
          zone: z.zone, x: sx, y: sy,
          in: [[-60, road], [cx, road], [cx, aisle], [sx, aisle], [sx, sy]],
          out: [[sx, sy], [sx, aisle], [cx, aisle], [cx, road], [-60, road]],
          ramp: [[sx, sy], [sx, aisle], [cx, aisle], [cx, apron], [rampX, apron], [rampX, quay + 34]],
        });
      }
    }
    return {
      W, H, slots, quay, rampX, ship: {x: 330, y: quay + 24, w: 560, h: 92},
      paint(g) {
        g.innerHTML = `
          <rect width="${W}" height="${quay}" fill="var(--t-ground)"/>
          <rect x="0" y="${road - 20}" width="${W}" height="40" fill="var(--t-road)"/>
          <line x1="0" x2="${W}" y1="${road}" y2="${road}" class="t-dash"/>
          ${zones.map(z => `
            <rect x="${z.x0}" y="96" width="540" height="${apron - 70}" rx="6" fill="var(--t-yard)"/>
            <rect x="${z.x0}" y="${aisle - 18}" width="540" height="36" fill="var(--t-road)"/>
            <rect x="${z.x0 + 6}" y="${road + 20}" width="36" height="${apron - road - 20}" fill="var(--t-road)"/>
            ${[160, 262].map(sy => Array.from({length: 11}, (_, i) =>
              `<line x1="${z.x0 + 51 + i * 50}" x2="${z.x0 + 51 + i * 50}" y1="${sy - 26}" y2="${sy + 26}" class="t-slot"/>`).join('')).join('')}
            <text x="${z.x0 + 52}" y="122" class="t-zone">${z.zone === 'KR' ? 'ТЕРМИНАЛ КОРЕЯ' : 'ТЕРМИНАЛ КИТАЙ'}</text>
            <text x="${z.x0 + 532}" y="122" class="t-zone-sub" text-anchor="end">${z.zone === 'KR' ? 'Encar · KB Chachacha' : 'Dongchedi · Che168'}</text>
          `).join('')}
          <rect x="0" y="${apron - 18}" width="${W}" height="36" fill="var(--t-road)"/>
          <line x1="0" x2="${W}" y1="${apron}" y2="${apron}" class="t-dash"/>
          ${gate(28, road, 'v')}
          <rect x="0" y="${quay}" width="${W}" height="${H - quay}" fill="var(--t-water)"/>
          <rect x="0" y="${quay - 6}" width="${W}" height="8" fill="url(#t-hazard)"/>
          ${bollards(W, quay)}`;
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
        zone: z.zone, x: sx, y: sy,
        in: [[lane, -50], [lane, sy], [sx, sy]],
        out: [[sx, sy], [lane, sy], [lane, -50]],
        ramp: [[sx, sy], [lane, sy], [lane, quay + 30]],
      });
    }
    return {
      W, H, slots, quay, rampX: lane, ship: {x: 34, y: quay + 26, w: 292, h: 60},
      paint(g) {
        g.innerHTML = `
          <rect width="${W}" height="${quay}" fill="var(--t-ground)"/>
          ${zones.map(z => `
            <rect x="16" y="${z.y0}" width="${W - 32}" height="236" rx="6" fill="var(--t-yard)"/>
            ${Array.from({length: 8}, (_, j) => `
              <line x1="${lane - 88}" x2="${lane - 30}" y1="${z.y0 + 21 + j * 30}" y2="${z.y0 + 21 + j * 30}" class="t-slot"/>
              <line x1="${lane + 30}" x2="${lane + 88}" y1="${z.y0 + 21 + j * 30}" y2="${z.y0 + 21 + j * 30}" class="t-slot"/>`).join('')}
            <text x="26" y="${z.y0 + 14}" class="t-zone">${z.zone === 'KR' ? 'КОРЕЯ' : 'КИТАЙ'}</text>
            <text x="${W - 26}" y="${z.y0 + 14}" class="t-zone-sub" text-anchor="end">${z.zone === 'KR' ? 'Encar · KB' : 'Dongchedi · Che168'}</text>
          `).join('')}
          <rect x="${lane - 18}" y="0" width="36" height="${quay}" fill="var(--t-road)"/>
          <line x1="${lane}" x2="${lane}" y1="0" y2="${quay}" class="t-dash"/>
          ${gate(lane, 26, 'h')}
          <rect x="0" y="${quay}" width="${W}" height="${H - quay}" fill="var(--t-water)"/>
          <rect x="0" y="${quay - 6}" width="${W}" height="8" fill="url(#t-hazard)"/>
          ${bollards(W, quay)}`;
      },
    };
  }

  // ворота со шлагбаумом: v — дорога горизонтальная (шлагбаум вертикальный), h — наоборот
  function gate(x, y, dir) {
    const booth = dir === 'v'
      ? `<rect x="${x - 9}" y="${y - 38}" width="18" height="14" rx="2" fill="var(--t-booth)"/>
         <rect x="${x - 2}" y="${y - 24}" width="4" height="30" rx="2" fill="url(#t-barrier)" class="t-barrier"/>`
      : `<rect x="${x + 22}" y="${y - 9}" width="14" height="18" rx="2" fill="var(--t-booth)"/>
         <rect x="${x - 6}" y="${y - 2}" width="28" height="4" rx="2" fill="url(#t-barrier-h)" class="t-barrier"/>`;
    return `<g class="t-gate">${booth}</g>`;
  }
  function bollards(W, quay) {
    let s = '';
    for (let x = 40; x < W; x += 80) s += `<circle cx="${x}" cy="${quay + 4}" r="3" fill="var(--t-bollard)"/>`;
    return s;
  }

  // --- силуэты сверху ----------------------------------------------------------
  // Нос машины смотрит вверх (−y); поворот считаем по направлению движения.
  const BODIES = {
    sedan: {l: 40, w: 19, cabin: [0.30, 0.70], r: 6},
    suv: {l: 42, w: 21, cabin: [0.26, 0.80], r: 5},
    hatch: {l: 34, w: 18, cabin: [0.30, 0.84], r: 6},
    van: {l: 45, w: 21, cabin: [0.16, 0.90], r: 5},
  };
  function carShape(d) {
    const b = BODIES[d.body] || BODIES.sedan;
    const l = b.l, w = b.w, x = -w / 2, y = -l / 2;
    const c0 = y + l * b.cabin[0], c1 = y + l * b.cabin[1];
    const dark = isDark(d.color);
    return `
      <rect class="car-glow" x="${x - 5}" y="${y - 5}" width="${w + 10}" height="${l + 10}" rx="${b.r + 4}"/>
      <rect x="${x + 1}" y="${y + 2}" width="${w}" height="${l}" rx="${b.r}" fill="rgba(0,0,0,.35)"/>
      <rect x="${x}" y="${y}" width="${w}" height="${l}" rx="${b.r}" fill="${d.color}" stroke="${dark ? 'rgba(255,255,255,.18)' : 'rgba(0,0,0,.25)'}" stroke-width="0.8"/>
      <path d="M${x + 2.5} ${c0} Q0 ${c0 - 4} ${-x - 2.5} ${c0} L${-x - 3.5} ${c0 + 5} L${x + 3.5} ${c0 + 5} Z" fill="var(--t-glass)"/>
      <rect x="${x + 3.5}" y="${c0 + 6}" width="${w - 7}" height="${c1 - c0 - 10}" rx="2.5" fill="${d.color}" stroke="rgba(0,0,0,.18)" stroke-width="0.6"/>
      <path d="M${x + 3.5} ${c1 - 3} L${-x - 3.5} ${c1 - 3} L${-x - 2.5} ${c1 + 1.5} Q0 ${c1 + 3.5} ${x + 2.5} ${c1 + 1.5} Z" fill="var(--t-glass)"/>
      <rect x="${x + 2}" y="${y + 0.6}" width="4" height="2" rx="1" fill="#fff6d6" opacity=".85"/>
      <rect x="${-x - 6}" y="${y + 0.6}" width="4" height="2" rx="1" fill="#fff6d6" opacity=".85"/>
      <rect x="${x + 2}" y="${-y - 2.4}" width="4" height="1.8" rx=".9" fill="#d3261f"/>
      <rect x="${-x - 6}" y="${-y - 2.4}" width="4" height="1.8" rx=".9" fill="#d3261f"/>`;
  }
  function isDark(hex) {
    const n = parseInt(hex.slice(1), 16);
    return ((n >> 16) * 299 + ((n >> 8) & 255) * 587 + (n & 255) * 114) / 1000 < 110;
  }

  // --- тестовые данные (?demo=1) ------------------------------------------------
  const DEMO = {
    KR: [['Kia K5', 'sedan'], ['Hyundai Sonata', 'sedan'], ['Kia Sportage', 'suv'], ['Hyundai Tucson', 'suv'],
      ['Kia Carnival', 'van'], ['Hyundai Avante', 'sedan'], ['Kia Seltos', 'suv'], ['Kia Ray', 'hatch'],
      ['Hyundai Santa Fe', 'suv'], ['Genesis G70', 'sedan'], ['Kia Sorento', 'suv'], ['Hyundai Staria', 'van']],
    CN: [['BYD Song Plus', 'suv'], ['Geely Monjaro', 'suv'], ['Changan UNI-K', 'suv'], ['Haval Jolion', 'suv'],
      ['Chery Tiggo 7', 'suv'], ['Geely Emgrand', 'sedan'], ['BYD Qin Plus', 'sedan'], ['Changan CS55', 'suv'],
      ['Toyota Camry', 'sedan'], ['Buick GL8', 'van'], ['Honda Fit', 'hatch'], ['Haval H6', 'suv']],
  };
  const DEMO_COLORS = ['#eceef0', '#eceef0', '#1c1e22', '#8a9099', '#c3c7cc', '#4b5058', '#2f5fa6', '#c62a24', '#f2eee4'];
  let demoSeq = 0;
  function demoCar(country) {
    const [title, body] = pick(DEMO[country]);
    demoSeq += 1;
    const price = Math.round(rnd(1.5, 3.6) * 20) * 50000;
    return {key: 'demo:' + demoSeq, source: 'demo', id: String(demoSeq), country, title, body, year: 2019 + Math.floor(rnd(0, 5)),
      price: price.toLocaleString('ru-RU').replace(/,/g, ' '), photo: null, path: null, verdict: 'ok', color: pick(DEMO_COLORS), demo: true};
  }

  // --- состояние сцены -----------------------------------------------------------
  let L, svg, gYard, gCars, gShip, deck;
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
      <pattern id="t-waves" width="60" height="22" patternUnits="userSpaceOnUse">
        <path d="M0 11 Q15 6 30 11 T60 11" fill="none" stroke="rgba(255,255,255,.07)" stroke-width="1.5"/></pattern>
    </defs><g class="t-yard"></g><rect class="t-waves" y="${L.quay}" width="${L.W}" height="${L.H - L.quay}" fill="url(#t-waves)"/>
    <g class="t-ship"></g><g class="t-cars"></g>`;
    root.prepend(svg);
    gYard = svg.querySelector('.t-yard');
    gCars = svg.querySelector('.t-cars');
    gShip = svg.querySelector('.t-ship');
    L.paint(gYard);
    if (!ship.loaded) ship.loaded = 3 + Math.floor(Math.random() * 5);
    paintShip();
    occupied = new Array(L.slots.length).fill(null);
  }

  function paintShip() {
    const s = L.ship, bow = s.x + s.w, mid = s.y + s.h / 2;
    const rows = s.h > 70 ? 3 : 2, cols = Math.floor((s.w - 120) / 26);
    deck = [];
    let marks = '';
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const x = s.x + 70 + c * 26, y = s.y + 14 + r * ((s.h - 28) / rows);
      deck.push([x, y]);
      marks += `<rect class="deck-car" x="${x}" y="${y}" width="22" height="${(s.h - 28) / rows - 5}" rx="3" opacity="0"/>`;
    }
    gShip.innerHTML = `<g class="ship-body">
      <path d="M${s.x} ${s.y + 6} Q${s.x} ${s.y} ${s.x + 6} ${s.y} L${bow - 60} ${s.y} Q${bow} ${s.y + 4} ${bow + 14} ${mid} Q${bow} ${s.y + s.h - 4} ${bow - 60} ${s.y + s.h} L${s.x + 6} ${s.y + s.h} Q${s.x} ${s.y + s.h} ${s.x} ${s.y + s.h - 6} Z" fill="var(--t-hull)"/>
      <rect x="${s.x + 6}" y="${s.y + 6}" width="${s.w - 40}" height="${s.h - 12}" rx="4" fill="var(--t-deck)"/>
      <rect x="${s.x + 12}" y="${s.y + 10}" width="44" height="${s.h - 20}" rx="3" fill="var(--t-bridge)"/>
      <rect x="${s.x + 18}" y="${s.y + 14}" width="6" height="${s.h - 28}" rx="2" fill="var(--t-glass)"/>
      ${marks}
      <text x="${bow - 34}" y="${mid + 4}" class="t-ship-name" text-anchor="end">RENAL · ВЛАДИВОСТОК</text>
    </g>`;
    gShip.querySelector('.ship-body').style.transform = `translateX(${ship.x}px)`;
    gShip.querySelectorAll('.deck-car').forEach((el, i) => { if (i < ship.loaded) el.setAttribute('opacity', '1'); });
  }

  // --- машины --------------------------------------------------------------------
  function freeSlot(zone) {
    const free = L.slots.map((s, i) => i).filter(i => L.slots[i].zone === zone && !occupied[i]);
    return free.length ? pick(free) : -1;
  }
  function makeCar(d) {
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'car');
    g.innerHTML = carShape(d);
    g.addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') showPop(car, false); });
    g.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse') hidePopSoon(); });
    g.addEventListener('click', () => { goal('car_click'); showPop(car, true); });
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
  function drive(car, path, state, done) {
    let len = 0;
    for (let i = 1; i < path.length; i++) len += Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]);
    Object.assign(car, {path, len, dist: 0, state, done});
    if (reduce.matches) { finish(car); return; }
    car.g.style.opacity = '';
    kick();
  }
  function finish(car) {
    const p = car.path[car.path.length - 1];
    const done = car.done;
    car.path = null;
    if (car.state === 'in') place(car, p[0], p[1], parkedAngle(car.slot));
    done && done();
  }
  function step(car, dt) {
    car.dist = Math.min(car.len, car.dist + SPEED * dt * (car.dist < 30 ? 0.6 + car.dist / 75 : 1));
    let rest = car.dist, i = 1;
    for (; i < car.path.length; i++) {
      const seg = Math.hypot(car.path[i][0] - car.path[i - 1][0], car.path[i][1] - car.path[i - 1][1]);
      if (rest <= seg || i === car.path.length - 1) {
        const t = seg ? Math.min(1, rest / seg) : 1, a = car.path[i - 1], b = car.path[i];
        const target = Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI + 90;
        let delta = ((target - car.ang + 540) % 360) - 180;
        const ang = car.ang + delta * Math.min(1, dt * 9);
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
    let slot = freeSlot(zone);
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
      return;
    }
    enter(d, slot);
  }
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
      toast(`<b>${esc(label(d))}</b> · прибыла на терминал`);
      hud();
    });
    hud();
  }
  function leave(car) {
    if (occupied[car.slot] === car.d.key) occupied[car.slot] = null;
    if (pop.car === car) hidePop();
    drive(car, L.slots[car.slot].out, 'out', () => remove(car));
    openGate();
  }
  function remove(car) {
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
    car.g.classList.add('chosen');
    drive(car, L.slots[car.slot].ramp, 'ramp', () => { car.state = 'at-ramp'; then && then(); });
  }
  function backToSlot(car) {
    car.g.classList.remove('chosen');
    drive(car, [...L.slots[car.slot].ramp].reverse(), 'back', () => {
      car.state = 'parked';
      place(car, L.slots[car.slot].x, L.slots[car.slot].y, parkedAngle(car.slot));
    });
  }
  function load(car) {
    occupied[car.slot] = null;
    car.g.classList.add('boarding');
    setTimeout(() => remove(car), reduce.matches ? 0 : 500);
    ship.loaded = Math.min(deck.length, ship.loaded + 1);
    gShip.querySelectorAll('.deck-car')[ship.loaded - 1]?.setAttribute('opacity', '1');
  }

  // --- судно: периодически уходит с машинами и приходит новое ------------------------
  function shipCycle() {
    if (reduce.matches || document.hidden || ship.state !== 'docked' || [...cars.values()].some(c => c.state === 'ramp' || c.state === 'at-ramp')) return;
    // перед отходом на борт заезжают 2–3 самые давние машины
    const old = [...cars.values()].filter(c => c.state === 'parked').sort((a, b) => a.since - b.since).slice(0, 3);
    old.forEach((c, i) => setTimeout(() => toRamp(c, () => load(c)), i * 900));
    setTimeout(() => {
      if ([...cars.values()].some(c => c.state === 'ramp' || c.state === 'at-ramp')) return;
      ship.state = 'leaving';
      toast('Судно ушло во Владивосток · <b>35–50 дней</b> до ключей');
      moveShip(L.W + 40, 7, () => {
        ship.loaded = 0;
        ship.x = -L.ship.x - L.ship.w - 60;
        paintShip();
        moveShip(0, 7, () => { ship.state = 'docked'; toast('Новое судно у причала · идёт погрузка'); });
      });
    }, old.length * 900 + 4500);
  }
  function moveShip(to, seconds, done) {
    const body = gShip.querySelector('.ship-body');
    body.style.transition = `transform ${seconds}s cubic-bezier(.45,.05,.4,1)`;
    requestAnimationFrame(() => { body.style.transform = `translateX(${to}px)`; });
    ship.x = to;
    setTimeout(() => { body.style.transition = ''; done(); }, seconds * 1000 + 50);
  }

  function frame(t) {
    const dt = Math.min(0.05, (t - last) / 1000 || 0);
    last = t;
    let moving = false;
    for (const car of cars.values()) if (car.path) { step(car, dt); moving = moving || !!car.path; }
    raf = moving ? requestAnimationFrame(frame) : 0;
  }
  function kick() { if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); } }

  // --- HUD и плашки ------------------------------------------------------------------
  const toasts = root.querySelector('.terminal-toasts');
  function toast(html) {
    const el = document.createElement('div');
    el.className = 'terminal-toast';
    el.innerHTML = html;
    toasts.prepend(el);
    while (toasts.children.length > 2) toasts.lastElementChild.remove();
    setTimeout(() => el.classList.add('out'), 3800);
    setTimeout(() => el.remove(), 4300);
  }
  function hud() {
    const list = [...cars.values()].filter(c => c.state !== 'out');
    const kr = list.filter(c => c.d.country !== 'CN').length;
    root.querySelector('[data-hud="count"]').textContent = L.W < 600
      ? `${list.length} машин · KR ${kr} · CN ${list.length - kr}`
      : `На терминале ${list.length} · Корея ${kr} · Китай ${list.length - kr}`;
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
    car.g.classList.add('hover');
    const d = car.d;
    const pill = d.verdict === 'warn' ? '<span class="pill warn">✓ Проходит, есть нюансы</span>' : '<span class="pill ok">✓ Проходит в РФ</span>';
    popEl.innerHTML = `
      ${d.photo ? `<div class="pop-ph"><img src="${esc(d.photo)}" alt=""></div>` : ''}
      ${d.demo ? '<div class="pop-demo">Тестовые данные</div>' : ''}
      <div class="pop-body">
        <b>${esc(label(d))}</b>
        <div class="pop-price">${d.price ? '≈ ' + esc(d.price) + ' ₽' : 'Цена по запросу'} <small>на площадке</small></div>
        ${pill}
        <div class="pop-actions">
          <button class="btn" type="button" data-act="calc">Узнать цену под ключ</button>
          <button class="btn ghost" type="button" data-act="want">Хочу эту</button>
        </div>
        ${d.path ? `<a class="small" href="${esc(d.path)}">Подробнее о машине →</a>` : ''}
      </div>`;
    popEl.querySelector('[data-act="calc"]').addEventListener('click', () => { hidePop(); openForm(d); });
    popEl.querySelector('[data-act="want"]').addEventListener('click', () => {
      hidePop();
      goal('car_want');
      let opened = false;
      const open = () => { if (!opened) { opened = true; openForm(d, car); } };
      toRamp(car, open);
      setTimeout(open, 2600);
    });
    popEl.hidden = false;
    position(car);
  }
  function position(car) {
    const r = car.g.getBoundingClientRect(), s = stage.getBoundingClientRect();
    const w = popEl.offsetWidth, h = popEl.offsetHeight;
    let left = r.left + r.width / 2 - s.left - w / 2;
    left = Math.max(4, Math.min(s.width - w - 4, left));
    let top = r.top - s.top - h - 10;
    if (top < 4) top = r.bottom - s.top + 10;
    popEl.style.left = left + 'px';
    popEl.style.top = top + 'px';
  }
  function hidePopSoon() { clearTimeout(pop.t); pop.t = setTimeout(hidePop, 260); }
  function hidePop() {
    clearTimeout(pop.t);
    pop.car?.g.classList.remove('hover');
    pop.car = null; pop.pinned = false;
    popEl.hidden = true;
  }

  // --- форма заявки с подставленной машиной ---------------------------------------------
  const dialog = document.getElementById('car-dialog');
  const form = dialog.querySelector('form');
  const blank = form.innerHTML;
  let formCar = null, sent = false;
  function openForm(d, car) {
    goal('form_open');
    if (!form.querySelector('[name="name"]')) form.innerHTML = blank; // после прошлой отправки
    form.querySelector('[data-car-name]').textContent = `${label(d)}${d.price ? ' · ≈ ' + d.price + ' ₽ на площадке' : ''}. Посчитаем доставку, таможню, утильсбор и оформление до вашего города.`;
    form.querySelector('[name="source"]').value = d.demo ? '' : d.source;
    form.querySelector('[name="external_id"]').value = d.demo ? '' : d.id;
    formCar = car || null;
    sent = false;
    dialog.showModal();
  }
  form.addEventListener('click', e => { if (e.target.closest('[data-close]')) dialog.close(); });
  dialog.addEventListener('click', e => { if (e.target === dialog) dialog.close(); });
  form.addEventListener('lead:sent', () => {
    sent = true;
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'btn ghost block'; close.dataset.close = ''; close.textContent = 'Вернуться к терминалу';
    form.appendChild(close);
  });
  dialog.addEventListener('close', () => {
    const car = formCar;
    formCar = null;
    if (!car || !cars.has(car.d.key)) return;
    if (sent) { load(car); toast('Заявка принята · менеджер посчитает цену под ключ'); }
    else if (car.state === 'at-ramp') backToSlot(car);
    else car.g.classList.remove('chosen');
  });

  // --- данные: стартовый набор, затем живая лента (или тестовый поток) -------------------
  function feed() {
    if (document.hidden) return;
    if (queue.length) { arrive(queue.shift()); return; }
    if (DATA.demo) arrive(demoCar(Math.random() < 0.5 ? 'KR' : 'CN'));
  }
  function connect() {
    if (DATA.demo) { setStatus(true, 'Тестовые данные'); return; }
    if (!window.EventSource) { setStatus(false, 'Терминал'); return; }
    const es = new EventSource('/api/stream');
    es.onopen = () => setStatus(true, 'Живая лента');
    es.onerror = () => setStatus(false, 'Переподключаемся…');
    es.addEventListener('new', async e => {
      const l = JSON.parse(e.data).listing;
      const res = await fetch(`/api/port/${encodeURIComponent(l.source)}/${encodeURIComponent(l.external_id)}`);
      if (res.status === 200) queue.unshift(await res.json());
    });
  }

  function init() {
    build();
    let start = DATA.cars.slice();
    if (DATA.demo && start.length < 24) {
      for (let i = start.length; i < 30; i++) start.push(demoCar(i % 2 ? 'CN' : 'KR'));
    }
    // машины из рекламной ссылки (?model=…) заезжают первыми, на глазах у посетителя
    const matched = DATA.match ? start.filter(d => d.title.toLowerCase().includes(DATA.match.toLowerCase())) : [];
    const rest = start.filter(d => !matched.includes(d));
    const parkNow = Math.round(L.slots.length * 0.6);
    rest.slice(0, parkNow).forEach(d => arrive(d, true));
    queue.push(...matched.slice(0, 4), ...rest.slice(parkNow), ...matched.slice(4));
    hud();
    connect();
    if (!reduce.matches) {
      setTimeout(feed, 900);
      setInterval(feed, 4200);
      setInterval(shipCycle, 42000);
    } else {
      queue.splice(0).forEach(d => arrive(d, true));
      setInterval(feed, 15000);
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
