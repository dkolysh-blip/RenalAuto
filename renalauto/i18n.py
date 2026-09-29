"""Перевод названий с корейского/китайского: марки и модели — латиницей, характеристики — по-русски."""

from __future__ import annotations

import re

MAKES: dict[str, str] = {
    # Корея
    "현대": "Hyundai", "기아": "Kia", "제네시스": "Genesis", "쉐보레": "Chevrolet", "GM대우": "Daewoo",
    "대우": "Daewoo", "르노코리아": "Renault Korea", "르노삼성": "Renault Samsung", "르노": "Renault",
    "KG모빌리티": "KG Mobility", "쌍용": "SsangYong", "벤츠": "Mercedes-Benz", "아우디": "Audi",
    "폭스바겐": "Volkswagen", "볼보": "Volvo", "토요타": "Toyota", "도요타": "Toyota", "렉서스": "Lexus",
    "혼다": "Honda", "닛산": "Nissan", "인피니티": "Infiniti", "포드": "Ford", "링컨": "Lincoln",
    "테슬라": "Tesla", "미니": "MINI", "포르쉐": "Porsche", "랜드로버": "Land Rover", "지프": "Jeep",
    "푸조": "Peugeot", "캐딜락": "Cadillac", "마세라티": "Maserati", "재규어": "Jaguar", "폴스타": "Polestar",
    # Китай
    "比亚迪": "BYD", "吉利汽车": "Geely", "吉利": "Geely", "长安": "Changan", "奇瑞": "Chery", "哈弗": "Haval",
    "长城": "Great Wall", "坦克": "Tank", "魏牌": "WEY", "大众": "Volkswagen", "丰田": "Toyota",
    "本田": "Honda", "日产": "Nissan", "奥迪": "Audi", "宝马": "BMW", "奔驰": "Mercedes-Benz",
    "别克": "Buick", "雪佛兰": "Chevrolet", "凯迪拉克": "Cadillac", "福特": "Ford", "马自达": "Mazda",
    "现代": "Hyundai", "起亚": "Kia", "特斯拉": "Tesla", "理想汽车": "Li Auto", "理想": "Li Auto",
    "蔚来": "NIO", "小鹏": "XPeng", "领克": "Lynk & Co", "红旗": "Hongqi", "五菱": "Wuling",
    "宝骏": "Baojun", "传祺": "Trumpchi", "广汽传祺": "Trumpchi", "埃安": "Aion", "荣威": "Roewe",
    "名爵": "MG", "沃尔沃": "Volvo", "雷克萨斯": "Lexus", "极氪": "Zeekr", "问界": "AITO",
    "捷途": "Jetour", "星途": "Exeed", "深蓝": "Deepal", "零跑": "Leapmotor", "路虎": "Land Rover",
    "保时捷": "Porsche", "斯柯达": "Skoda", "标致": "Peugeot", "雪铁龙": "Citroën", "三菱": "Mitsubishi",
    "斯巴鲁": "Subaru", "英菲尼迪": "Infiniti", "林肯": "Lincoln", "极狐": "Arcfox", "岚图": "Voyah",
    "腾势": "Denza", "方程豹": "Fangchengbao", "东风": "Dongfeng", "北京": "BAIC", "奔腾": "Bestune",
}

MODELS: dict[str, str] = {
    # Hyundai / Genesis
    "아반떼": "Avante", "쏘나타": "Sonata", "그랜저": "Grandeur", "팰리세이드": "Palisade", "싼타페": "Santa Fe",
    "투싼": "Tucson", "코나": "Kona", "베뉴": "Venue", "캐스퍼": "Casper", "스타리아": "Staria",
    "스타렉스": "Starex", "포터": "Porter", "아이오닉": "Ioniq", "넥쏘": "Nexo", "엑센트": "Accent",
    "벨로스터": "Veloster", "맥스크루즈": "Maxcruz", "제네시스": "Genesis", "에쿠스": "Equus",
    # Kia
    "쏘렌토": "Sorento", "스포티지": "Sportage", "셀토스": "Seltos", "니로": "Niro", "카니발": "Carnival",
    "모닝": "Morning", "레이": "Ray", "스팅어": "Stinger", "모하비": "Mohave", "봉고": "Bongo",
    "쏘울": "Soul", "카렌스": "Carens", "스토닉": "Stonic",
    # Chevrolet / Renault / SsangYong
    "스파크": "Spark", "말리부": "Malibu", "트랙스": "Trax", "트레일블레이저": "Trailblazer",
    "이쿼녹스": "Equinox", "볼트": "Bolt", "크루즈": "Cruze", "그랑 콜레오스": "Grand Koleos",
    "콜레오스": "Koleos", "아르카나": "Arkana", "티볼리": "Tivoli", "코란도": "Korando", "렉스턴": "Rexton",
    "토레스": "Torres",
    # Импорт в Корее
    "5시리즈": "5 Series", "3시리즈": "3 Series", "7시리즈": "7 Series", "E-클래스": "E-Class",
    "C-클래스": "C-Class", "S-클래스": "S-Class",
    # Китай
    "汉": "Han", "唐": "Tang", "宋": "Song", "秦": "Qin", "元": "Yuan", "海豹": "Seal", "海豚": "Dolphin",
    "海鸥": "Seagull", "凯美瑞": "Camry", "卡罗拉": "Corolla", "雷凌": "Levin", "汉兰达": "Highlander",
    "亚洲龙": "Avalon", "思域": "Civic", "雅阁": "Accord", "凌派": "Crider", "轩逸": "Sylphy",
    "天籁": "Teana", "奇骏": "X-Trail", "逍客": "Qashqai", "帕萨特": "Passat", "迈腾": "Magotan",
    "速腾": "Sagitar", "朗逸": "Lavida", "宝来": "Bora", "途观": "Tiguan", "探岳": "Tayron", "途昂": "Teramont",
    "星越": "Xingyue", "博越": "Boyue", "帝豪": "Emgrand", "星瑞": "Preface", "CS75": "CS75",
    "瑞虎": "Tiggo", "艾瑞泽": "Arrizo", "大狗": "Dargo", "H6": "H6", "英朗": "Excelle", "君威": "Regal",
    "君越": "LaCrosse", "昂科威": "Envision", "蒙迪欧": "Mondeo", "探险者": "Explorer",
}

TERMS: dict[str, str] = {
    # Корейские
    "더 뉴": "The New", "올 뉴": "All New", "디 올 뉴": "The All New", "신형": "new", "가솔린": "бензин",
    "디젤": "дизель", "하이브리드": "гибрид", "전기": "электро", "터보": "Turbo", "인승": " мест",
    "프리미엄": "Premium", "프레스티지": "Prestige", "노블레스": "Noblesse", "시그니처": "Signature",
    "인스퍼레이션": "Inspiration", "캘리그래피": "Calligraphy", "익스클루시브": "Exclusive", "모던": "Modern",
    "스마트": "Smart", "럭셔리": "Luxury", "트렌디": "Trendy", "스타일": "Style", "스페셜": "Special",
    "그래비티": "Gravity", "블랙": "Black", "에디션": "Edition", "스포츠": "Sport", "초장축": "long",
    "킹캡": "King Cab", "톤": "t", "밴": "Van",
    # Китайские
    "款": " г.", "改款": "рестайлинг", "豪华型": "Luxury", "舒适型": "Comfort", "精英型": "Elite",
    "尊贵型": "Premium", "旗舰型": "Flagship", "进取型": "Progressive", "两驱": "2WD", "四驱": "4WD",
    "自动": "АКПП", "手动": "МКПП", "纯电动": "электро", "插电混动": "PHEV", "混动": "гибрид",
    "豪华": "Luxury", "舒适": "Comfort", "精英": "Elite", "尊贵": "Premium", "旗舰": "Flagship",
    "进取": "Progressive", "创世": "Genesis", "尊享": "Premium", "运动": "Sport", "时尚": "Fashion",
    "领先": "Leading", "标准": "Standard", "超长续航": "Long Range", "长续航": "Long Range",
    "版": "", "型": "",
}

FUEL: dict[str, str] = {
    "가솔린": "Бензин", "디젤": "Дизель", "하이브리드(가솔린)": "Гибрид (бензин)", "하이브리드(디젤)": "Гибрид (дизель)",
    "하이브리드": "Гибрид", "전기": "Электро", "LPG": "Газ (LPG)", "가솔린+LPG": "Бензин + газ", "수소": "Водород",
    "汽油": "Бензин", "柴油": "Дизель", "油电混合": "Гибрид", "插电式混合动力": "Подключаемый гибрид",
    "纯电动": "Электро", "增程式": "Гибрид с увеличителем запаса хода",
}

TRANSMISSION: dict[str, str] = {
    "오토": "Автомат", "수동": "Механика", "CVT": "Вариатор", "세미오토": "Робот",
    "自动": "Автомат", "手动": "Механика",
}

CITIES: dict[str, str] = {
    "서울": "Сеул", "경기": "Кёнгидо", "인천": "Инчхон", "부산": "Пусан", "대구": "Тэгу", "대전": "Тэджон",
    "광주": "Кванджу", "울산": "Ульсан", "세종": "Седжон", "강원": "Канвондо", "충북": "Чхунчхон-Пукто",
    "충남": "Чхунчхон-Намдо", "전북": "Чолла-Пукто", "전남": "Чолла-Намдо", "경북": "Кёнсан-Пукто",
    "경남": "Кёнсан-Намдо", "제주": "Чеджу",
    "北京": "Пекин", "上海": "Шанхай", "广州": "Гуанчжоу", "深圳": "Шэньчжэнь", "成都": "Чэнду",
    "杭州": "Ханчжоу", "重庆": "Чунцин", "天津": "Тяньцзинь", "武汉": "Ухань", "西安": "Сиань",
    "南京": "Нанкин", "苏州": "Сучжоу", "郑州": "Чжэнчжоу", "长沙": "Чанша", "沈阳": "Шэньян",
    "哈尔滨": "Харбин", "青岛": "Циндао", "大连": "Далянь",
}

BODY: dict[str, str] = {
    "경차": "Микро", "소형": "Малый класс", "준중형": "Компакт", "중형": "Средний класс", "대형": "Бизнес-класс",
    "SUV": "Внедорожник/кроссовер", "RV": "Минивэн", "승합": "Микроавтобус", "트럭": "Грузовик",
    "스포츠카": "Спорткар", "쿠페": "Купе", "컨버터블": "Кабриолет",
}

COLORS: dict[str, str] = {
    "흰색": "Белый", "검정색": "Чёрный", "회색": "Серый", "은색": "Серебристый", "쥐색": "Тёмно-серый",
    "진주색": "Перламутровый", "파랑": "Синий", "청색": "Синий", "빨강": "Красный", "갈색": "Коричневый",
    "녹색": "Зелёный", "노랑": "Жёлтый", "주황": "Оранжевый",
}

_ALL_TITLE = {**MAKES, **MODELS, **TERMS}
_TITLE_KEYS = sorted(_ALL_TITLE, key=len, reverse=True)
_TITLE_RE = re.compile("|".join(re.escape(k) for k in _TITLE_KEYS))
_NON_LATIN_RE = re.compile(r"[가-힣一-鿿]")


def _lookup(table: dict[str, str], value: str | None) -> str | None:
    if not value:
        return value
    value = value.strip()
    if value in table:
        return table[value]
    for key in sorted(table, key=len, reverse=True):
        if key in value:
            return table[key]
    return value


def title(text: str | None) -> str:
    """'현대 팰리세이드 3.8 가솔린 8인승 프레스티지' -> 'Hyundai Palisade 3.8 бензин 8 мест Prestige'."""
    if not text:
        return ""
    out = _TITLE_RE.sub(lambda m: f" {_ALL_TITLE[m.group()]} ", text)
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r"(\d)\s+мест", r"\1 мест", out)
    out = re.sub(r"(\d)\s+г\.", r"\1 г.", out)
    out = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", out))
    return out


def make(value: str | None) -> str | None:
    return _lookup(MAKES, value)


def model(value: str | None) -> str | None:
    if not value:
        return value
    translated = title(value)
    return translated or value


def fuel(value: str | None) -> str | None:
    return _lookup(FUEL, value)


def transmission(value: str | None) -> str | None:
    return _lookup(TRANSMISSION, value)


def city(value: str | None) -> str | None:
    if not value:
        return value
    translated = _lookup(CITIES, value)
    return translated


def body(value: str | None) -> str | None:
    return _lookup(BODY, value)


def color(value: str | None) -> str | None:
    if not value:
        return value
    base = re.sub(r"\(.*?\)", "", value).strip()
    return _lookup(COLORS, base)


def has_foreign(text: str | None) -> bool:
    return bool(text and _NON_LATIN_RE.search(text))


def search_aliases(term: str) -> list[str]:
    """Все написания марки/модели для поиска: 'hyundai' -> ['hyundai', '현대', '现代']."""
    term_l = term.strip().lower()
    aliases = {term.strip()}
    for native, latin in {**MAKES, **MODELS}.items():
        if latin.lower() == term_l or native == term.strip():
            aliases.add(native)
            aliases.add(latin)
    return sorted(a for a in aliases if a)
