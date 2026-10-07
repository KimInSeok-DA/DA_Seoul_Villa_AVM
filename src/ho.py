"""호 표기 통일 — 공시가격 정제(build_apt_price.py)와 예측(avm.py)이 같은 규칙을 쓴다.
표준 라이브러리만 쓴다(predict.py 실행에 수집용 패키지가 필요 없게)."""
import re

SPELLED = [("에이", "A"), ("비이", "B"), ("비", "B"), ("씨", "C"), ("디", "D")]
FLOOR_PREFIX = re.compile(r"^(지상|지하|지층|지)?\d+층-?")
BASEMENT_PREFIX = re.compile(r"^(지하층|지층|지하|지)")
DONG_PREFIX = re.compile(r"(\d{1,4}동-?|\d{3,4}-|[A-Z가-힣]{1,2}-?)(\d{3,4})")


def ho_key(ho, floor):
    """호 표기 통일(입력 `ho`와 맞추기 위한 키)과 호 앞 동 표시를 돌려준다: (ho_key, ho_prefix)

    '301'·'3층301호'·'301(3층)'·'3층(101)'·'제301' → '301', 'B01'·'비01'·'지층B01'·'지하층비01'·'지01' → 'B1',
    '3층1' → '301', '1층가'·'지상1층에이세대' → '1가'·'1A', '2-1' → '2-1',
    '101동201'·'101-201'·'나201'·'A 101' → '201'·'201'·'201'·'101' (앞 표시는 ho_prefix)
    """
    raw = str(ho).strip().replace(" ", "")
    outside = re.sub(r"\(.*?\)", "", raw)
    inside = "".join(re.findall(r"\((.*?)\)", raw))
    out_rest = FLOOR_PREFIX.sub("", outside)
    # '301(3층)'은 바깥이 호, '3층(101)'·'일층(101)'은 괄호 안이 호
    if re.search(r"\d", inside) and not re.search(r"\d", out_rest):
        s = inside
    else:
        # 괄호 안이 숫자 없는 표시('(지층)' 등)면 바깥에 숫자가 있을 때 버린다
        s = outside if re.search(r"\d", outside) else outside + inside
    basement = floor < 0 or bool(re.match(r"^(지층|지하|지\d)", s))
    had_floor = bool(FLOOR_PREFIX.match(s))
    s = FLOOR_PREFIX.sub("", s)
    s = re.sub(r"(호|세대|형)$", "", s).replace("호", "")
    s = re.sub(r"^제", "", s)
    while basement and BASEMENT_PREFIX.match(s):
        s = BASEMENT_PREFIX.sub("", s, count=1)
    for k, v in SPELLED:
        s = s.replace(k, v)
    s = s.upper().strip("-")
    if re.fullmatch(r"B?\d+", s):
        n = int(s.lstrip("B"))
        if basement or s.startswith("B"):
            return f"B{n}", ""
        return (f"{floor}{n:02d}" if had_floor and n < 100 else str(n)), ""
    m = DONG_PREFIX.fullmatch(s)
    if m and not (basement and m.group(1) == "B"):
        n = int(m.group(2))
        return (f"B{n}" if basement else str(n)), m.group(1).rstrip("-")
    if re.fullmatch(r"\d+-\d+", s):
        a, b = s.split("-")
        return f"{int(a)}-{int(b)}", ""
    s = re.sub(r"동$", "", s)
    if not s:
        return (f"B{abs(floor)}" if basement else str(floor)), ""
    if re.fullmatch(r"[A-Z가-힣]", s):  # 층 + 문자 하나
        return f"{'B' if basement else ''}{abs(floor) if basement else floor}{s}", ""
    return ("B" if basement and not s.startswith("B") else "") + s, ""
