"""Разведка площадок с сервера: что отдают, не блокируют ли, где данные.

Запуск на сервере:  docker compose exec -T renalauto python -m renalauto.probe
Вывод короткий — его можно целиком прислать разработчику.
"""

from __future__ import annotations

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


if __name__ == "__main__":
    main()
