# -*- coding: utf-8 -*-
"""OX 치환 전수 검사.
   fact의 [[정답]]을 distractor로 바꿨을 때 문장이 깨지지 않는지 본다.
   앱은 이 치환으로 OX 문제를 자동 생성하므로, 여기서 걸러내지 못하면
   사용자가 '오키섬를', '약 약 87,554㎡' 같은 문장을 그대로 보게 된다."""
import json, re, sys

FILL = re.compile(r'\[\[(.+?)\]\]')

def batchim(word):
    """마지막 글자에 받침이 있는지. (있으면 True) 숫자·영문도 읽는 소리로 판정."""
    w = word.rstrip().rstrip('.,)]"\'')
    if not w: return False
    c = w[-1]
    if '가' <= c <= '힣':
        return (ord(c) - 0xAC00) % 28 != 0
    # 숫자는 읽는 소리 기준
    num = {'0':True,'1':True,'2':False,'3':True,'4':False,'5':False,
           '6':True,'7':True,'8':True,'9':False}
    if c in num: return num[c]
    # 단위는 읽는 소리로 판정한다. m은 '미터', km은 '킬로미터'라 받침이 없다.
    UNIT = {"㎡":False,"m":False,"km":False,"cm":False,"kg":False,"g":False,
            "t":False,"L":False,"%":False,"℃":False,"해리":False,"마일":False}
    for u in sorted(UNIT, key=len, reverse=True):
        if w.endswith(u): return UNIT[u]
    if c.isalpha(): return c.lower() in 'bcdfgjklnpqrstvxz'
    return False

def rieul(word):
    w = word.rstrip().rstrip('.,)]"\'')
    if not w: return False
    c = w[-1]
    if '가' <= c <= '힣':
        return (ord(c) - 0xAC00) % 28 == 8   # 종성 ㄹ
    return c in '1lL'   # 1(일), l

PAIRS = [("을","를"),("이","가"),("은","는"),("과","와"),("이다","다"),
         ("이었","였"),("으로","로"),("이나","나"),("이라","라"),("이며","며")]

def check(items, label):
    bad, warn = [], []
    for q in items:
        m = FILL.search(q.get("fact",""))
        if not m:
            bad.append((q["id"], "마킹 없음", "")); continue
        val, dis = m.group(1), q.get("distractor","")
        head, tail = q["fact"][:m.start()], q["fact"][m.end():]
        ox = head + dis + tail

        # ① 조사 일치
        for c_form, v_form in PAIRS:
            if tail.startswith(c_form) and not tail.startswith(v_form):
                if not batchim(dis):
                    bad.append((q["id"], f"조사 오류 '{dis}{c_form}'", ox)); break
            elif tail.startswith(v_form):
                if batchim(dis) and (v_form, c_form) != ("로","으로"):
                    bad.append((q["id"], f"조사 오류 '{dis}{v_form}'", ox)); break
        # ②/③ 으로·로
        if tail.startswith("으로") and not batchim(dis):
            bad.append((q["id"], f"'{dis}으로'", ox))
        if tail.startswith("로") and not tail.startswith("로서") and batchim(dis) and not rieul(dis):
            bad.append((q["id"], f"'{dis}로'", ox))

        # ④ 중복 표현
        for w in ["약","총","제","모두","각각"]:
            if re.search(rf'\b{w}\s+{w}\b', ox) or f"{w} {w}" in ox:
                warn.append((q["id"], f"중복 '{w} {w}'", ox))
        if re.search(r'(하기|되기|시키기)\1', ox):
            warn.append((q["id"], "동사 중복", ox))

        # ⑤ 정답과 오답이 같으면 OX가 성립하지 않음
        if dis.strip() == val.strip():
            bad.append((q["id"], "distractor가 정답과 동일", ox))
        # ⑥ 보기 중복
        bd = q.get("blankDistractors") or []
        if val in bd:
            bad.append((q["id"], "blankDistractors에 정답 포함", ""))
        if len(set(bd)) != len(bd):
            warn.append((q["id"], "blankDistractors 중복", ""))

    print(f"\n── {label} ({len(items)}문항)")
    print(f"   치환 파손 {len(bad)}건 / 경고 {len(warn)}건")
    for i,(qid,why,ox) in enumerate(bad):
        print(f"   [파손] id={qid} {why}")
        if ox: print(f"          → {ox}")
        if i>=14: print(f"   ... 외 {len(bad)-15}건"); break
    for i,(qid,why,ox) in enumerate(warn):
        print(f"   [경고] id={qid} {why}")
        if ox: print(f"          → {ox}")
        if i>=14: print(f"   ... 외 {len(warn)-15}건"); break
    return len(bad)

def load(p):
    d = json.load(open(p, encoding="utf-8"))
    return d["questions"] if isinstance(d, dict) else d

if __name__ == "__main__":
    new = load("merged.json")
    old = load("new36.json")
    b1 = check(new, "전체 121문항")
    b2 = check(old, "신규 36문항")
    print("\n" + "="*46)
    print(f"신규 파손 {b1}건 · 기존 파손 {b2}건")
    sys.exit(0 if b1 == 0 else 1)
