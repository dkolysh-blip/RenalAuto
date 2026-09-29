"""Разведка площадок с сервера: что отдают, не блокируют ли, где данные.

Запуск на сервере:  docker compose exec -T renalauto python -m renalauto.probe
Вывод короткий — его можно целиком прислать разработчику.
"""

from __future__ import annotations

import json
import re

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"


def squeeze(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def show(title: str, response: httpx.Response | Exception, markers: list[str] = (), around: int = 700, limit: int = 1) -> str:
    print(f"\n=== {title}")
    if isinstance(response, Exception):
        print(f"ERROR {type(response).__name__}: {response}")
        return ""
    text = response.text
    print(f"{response.status_code} {len(text)}b {response.headers.get('content-type', '')} -> {response.url}")
    flat = squeeze(text)
    if "blocked" in flat.lower() or "captcha" in flat.lower() or "验证" in flat:
        print("!! похоже на блокировку/капчу:", flat[:300])
    found = False
    for marker in markers:
        for m in list(re.finditer(re.escape(marker), flat))[:limit]:
            found = True
            print(f"[{marker}] …{flat[max(0, m.start() - 150): m.start() + around]}…")
    if not found:
        print("начало:", flat[:500])
    return text


def get(client: httpx.Client, url: str, **kw):
    try:
        return client.get(url, **kw)
    except Exception as exc:  # noqa: BLE001
        return exc


def main() -> None:
    c = httpx.Client(headers={"User-Agent": UA, "Accept-Language": "ko,zh;q=0.9,en;q=0.8"}, timeout=20, follow_redirects=True)
    m = httpx.Client(headers={"User-Agent": MOBILE_UA}, timeout=20, follow_redirects=True)

    # --- Encar -----------------------------------------------------------------
    show("ENCAR api (блокировка облачных IP?)", get(c, "https://api.encar.com/search/car/list/premium",
         params={"count": "true", "q": "(And.Hidden.N._.CarType.Y.)", "sr": "|ModifiedDate|0|2"},
         headers={"Referer": "https://www.encar.com/"}), ["SearchResults"], 300)
    show("ENCAR www список (HTML)", get(c, "https://www.encar.com/dc/dc_carsearchlist.do?carType=kor"), ["carid", "Price", "api.encar"], 300)
    show("ENCAR mobile", get(m, "https://m.encar.com/"), ["api.encar", "carid"], 300)

    # --- KB Chachacha: где история (보험이력) --------------------------------------
    listing = get(c, "https://www.kbchachacha.com/public/search/list.empty", params={"page": 1, "sort": "-orderDate"},
                  headers={"Referer": "https://www.kbchachacha.com/public/search/main.kbc", "X-Requested-With": "XMLHttpRequest"})
    seq = None
    if not isinstance(listing, Exception):
        found = re.findall(r'data-car-seq="(\d+)"', listing.text)
        seq = found[-1] if found else None
    if seq:
        detail = get(c, "https://www.kbchachacha.com/public/car/detail.kbc", params={"carSeq": seq})
        if not isinstance(detail, Exception):
            flat = squeeze(detail.text)
            print(f"\n=== KB карточка {seq}: ссылки/ajax про историю и осмотр")
            urls = sorted(set(re.findall(r"""['"](/[\w/.-]*(?:history|History|sago|insur|Insur|check|Check|perform|Perform|record|Record)[\w/.-]*\.(?:kbc|json|do|empty))""", flat)))
            print("\n".join(urls[:30]) or "не найдено")
            for kw in ("보험이력", "사고이력", "성능점검", "차대번호"):
                for mm in list(re.finditer(kw, flat))[:1]:
                    print(f"[{kw}] …{flat[max(0, mm.start() - 200): mm.start() + 400]}…")

    # --- K Car -----------------------------------------------------------------
    kcar = show("K CAR главная", get(c, "https://www.kcar.com/"), ["api.kcar.com"], 200)
    if kcar:
        print("api:", sorted(set(re.findall(r"https?://api[\w.-]*kcar\.com[\w/.-]*", kcar)))[:15])
    show("K CAR поиск", get(c, "https://www.kcar.com/bc/search"), ["carCd", "prc", "api"], 300)

    # --- Che168 ----------------------------------------------------------------
    show("CHE168 PC список", get(c, "https://www.che168.com/china/list/"), ["infoid", "cards-li", "carname"], 900)
    show("CHE168 mobile", get(m, "https://m.che168.com/china/list/"), ["infoid", "carname", "price"], 500)
    show("CHE168 api", get(m, "https://api2scsou.che168.com/api/v11/search",
         params={"pageindex": 1, "pagesize": 2, "ishideback": 1, "cid": 0}), ["carlist", "infoid", "returncode"], 600)

    # --- Guazi -----------------------------------------------------------------
    show("GUAZI", get(c, "https://www.guazi.com/buy"), ["clueId", "carList", "__NEXT_DATA__", "title"], 400)
    show("GUAZI mobile", get(m, "https://m.guazi.com/buy"), ["clueId", "carList", "title"], 400)

    # --- Dongchedi (работает) — карточка: есть ли VIN/отчёт ----------------------
    show("DONGCHEDI карточка", get(c, "https://www.dongchedi.com/usedcar/1"), ["vin", "VIN", "检测报告"], 300)


def _next_data_summary(html: str) -> None:
    """Что лежит в данных Next.js/Nuxt, которые сайт встраивает в HTML (их можно читать без API)."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        print("__NEXT_DATA__ нет")
        return
    raw = m.group(1)
    print(f"__NEXT_DATA__ {len(raw)}b")
    for key in ("carid", "carId", "vehicleId", "vin", "vehicleNo", "Price", "price", "Mileage", "mileage",
                "FormYear", "yearMonth", "manufacturerName", "Manufacturer", "photos", "accident"):
        mm = re.search(r'"%s"\s*:' % key, raw)
        if mm:
            print(f"  [{key}] …{squeeze(raw[max(0, mm.start() - 80): mm.start() + 220])}…")


def step2() -> None:
    c = httpx.Client(headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"}, timeout=25, follow_redirects=True)

    home = get(c, "https://car.encar.com/")
    carids: list[str] = []
    if not isinstance(home, Exception):
        carids = list(dict.fromkeys(re.findall(r'carid(?:&quot;|\\?")\s*:\s*(?:&quot;|\\?")(\d+)', home.text)))
        print("\n=== car.encar.com: ссылки на списки")
        print(sorted(set(re.findall(r'href="(/list/[^"]{0,120})"', home.text)))[:15])
        _next_data_summary(home.text)
    carid = carids[0] if carids else "41867777"
    print("carid для проверки:", carid)

    for title, url in [
        ("car.encar.com список отечественных", "https://car.encar.com/list/car?page=1&search=%7B%22type%22%3A%22car%22%2C%22action%22%3A%22(And.Hidden.N._.CarType.A.)%22%2C%22title%22%3A%22%EA%B5%AD%EC%82%B0%22%2C%22toggle%22%3A%7B%7D%2C%22layer%22%3A%22%22%2C%22sort%22%3A%22ModifiedDate%22%7D"),
        ("fem.encar.com карточка", f"https://fem.encar.com/cars/detail/{carid}"),
        ("www.encar.com карточка (старая)", f"https://www.encar.com/dc/dc_cardetailview.do?carid={carid}"),
        ("fem.encar.com отчёт о ДТП", f"https://fem.encar.com/cars/report/accident/{carid}"),
    ]:
        r = show(title, get(c, url), ["vin", "vehicleNo", "carid", "Price"], 250)
        if r:
            _next_data_summary(r)

    # K Car: ищем адреса API в скриптах сайта
    page = get(c, "https://www.kcar.com/bc/search")
    if not isinstance(page, Exception):
        scripts = list(dict.fromkeys(re.findall(r'src="(/_nuxt/[\w.-]+\.js)"', page.text)))
        print(f"\n=== K CAR: скриптов {len(scripts)}")
        found: set[str] = set()
        for src in scripts[:40]:
            js = get(c, "https://www.kcar.com" + src)
            if isinstance(js, Exception):
                continue
            found.update(re.findall(r'["\'`](/bc/[\w/-]*(?:search|list|car)[\w/-]*)["\'`]', js.text))
            found.update(re.findall(r'https?://api[\w.-]*\.kcar\.com[\w/-]*', js.text))
        print("\n".join(sorted(found)[:60]) or "не найдено")


def step3() -> None:
    """K Car: как сайт вызывает API списка машин и что оно отвечает."""
    c = httpx.Client(headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"}, timeout=25, follow_redirects=True)
    page = get(c, "https://www.kcar.com/bc/search")
    if isinstance(page, Exception):
        print("ERROR", page)
        return
    scripts = list(dict.fromkeys(re.findall(r'src="(/_nuxt/[\w.-]+\.js)"', page.text)))
    markers = ("search/list/drct", "IntgSearchList", "search/carList", "api.kcar.com", "baseURL", "wr_", "pageno", "pageNo")
    shown = 0
    for src in scripts:
        js = get(c, "https://www.kcar.com" + src)
        if isinstance(js, Exception):
            continue
        text = js.text
        for marker in markers:
            for m in list(re.finditer(re.escape(marker), text))[:2]:
                if shown >= 14:
                    break
                shown += 1
                print(f"\n[{src} :: {marker}] …{squeeze(text[max(0, m.start() - 250): m.start() + 450])}…")

    print("\n=== K CAR пробные запросы к API")
    headers = {"Referer": "https://www.kcar.com/bc/search", "Origin": "https://www.kcar.com", "Accept": "application/json, text/plain, */*"}
    body = {"wr_eq_sell_dcd": "ALL", "wr_in_multi_columns": "cntr_rgn_cd|cntr_cd", "wr_in_cntr_rgn_cd": "", "pageno": 1, "limit": 3, "sort": "car_prce"}
    for method, url in [
        ("POST", "https://api.kcar.com/bc/search/list/drct"),
        ("POST", "https://api.kcar.com/bc/search/list"),
        ("GET", "https://api.kcar.com/bc/search/list/drct?pageno=1&limit=3"),
        ("POST", "https://www.kcar.com/bc/search/list/drct"),
    ]:
        try:
            r = c.request(method, url, json=body if method == "POST" else None, headers=headers)
            print(f"{method} {url} -> {r.status_code} {r.headers.get('content-type', '')} :: {squeeze(r.text)[:400]}")
        except Exception as exc:  # noqa: BLE001
            print(f"{method} {url} -> ERROR {exc}")


def step4() -> None:
    """K Car: сам вызов API списка и перебор вариантов тела запроса."""
    c = httpx.Client(headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"}, timeout=25, follow_redirects=True)
    page = get(c, "https://www.kcar.com/bc/search")
    if isinstance(page, Exception):
        print("ERROR", page)
        return
    scripts = list(dict.fromkeys(re.findall(r'src="(/_nuxt/[\w.-]+\.js)"', page.text)))
    for src in scripts:
        js = get(c, "https://www.kcar.com" + src)
        if isinstance(js, Exception):
            continue
        for m in list(re.finditer(r"list/drct", js.text))[:3]:
            print(f"\n[{src}] …{squeeze(js.text[max(0, m.start() - 700): m.start() + 500])}…")

    print("\n=== K CAR варианты запроса")
    headers = {"Referer": "https://www.kcar.com/", "Origin": "https://www.kcar.com",
               "Accept": "application/json, text/plain, */*", "Content-Type": "application/json;charset=UTF-8"}
    order = "time_deal_yn:desc|time_deal_end_dt:asc|promo_ordr:asc|event_ordr:asc|sort_ordr:asc"
    bodies = [
        {"pageno": 1, "limit": 3},
        {"wr_eq_sell_dcd": "ALL", "pageno": 1, "limit": 3, "orderFlag": True, "orderBy": order},
        {"wr_eq_sell_dcd": "ALL", "wr_not_eq_csgmt_yn": "B", "pageno": 1, "limit": 3, "orderFlag": True, "orderBy": order},
        {"wr_eq_sell_dcd": "ALL", "pageno": 1, "limit": 3, "orderFlag": True, "orderBy": "sort_ordr:asc"},
    ]
    for url in ("https://api.kcar.com/bc/search/list/drct", "https://api.kcar.com/bc/search/list/acm"):
        for body in bodies:
            try:
                r = c.post(url, json=body, headers=headers)
                print(f"POST {url.rsplit('/', 1)[-1]} {json.dumps(body)[:120]} -> {r.status_code} :: {squeeze(r.text)[:500]}")
            except Exception as exc:  # noqa: BLE001
                print(f"POST {url} -> ERROR {exc}")


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    step4() if "step4" in args else step3() if "step3" in args else step2() if "step2" in args else main()
