#!/usr/bin/env python3
"""독도 스쿨 문항 검사기 v2. Python 3.9+, 표준 라이브러리만 사용.

python validate.py questions.json
python validate.py batch.json questions.json
종료 코드: 0 통과, 1 검증 실패, 2 파일/명령행 오류.

'개별보기_교차추출금지'는 공유 풀이 아닌 안전 예외이다.
면적·우편번호·인원·기간·톤수 등의 희소 유형은 기존 85문항만으로
의미를 보존하며 각각 3문항 이상으로 나눌 수 없다. 억지로 합치지 않는다.
신규 문항은 blankDistractors에 문항별 빈칸 오답 3개를 반드시 제공한다.
기존에 blankDistractors가 없는 문항은 원래 4지선다만 사용한다.
앱 출제기도 해당 필드를 직접 사용하도록 수정해야 하며, 이 검사기는 앱을 수정하지 않는다.
검사기 교체나 atype 매핑만으로 앱 출제 코드가 변경되지는 않는다.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

VALID_GRADES = {
    "K", "E1", "E2", "E3", "E4", "E5", "E6",
    "M1", "M2", "M3", "H1", "H2", "H3",
    "U1", "U2", "U3", "U4", "MA1", "MA2", "PHD1", "PHD2",
}
VALID_CATS = {"자연생태", "현대주권", "역사문헌", "인물", "국제법"}
BASE_ATYPES = {
    "연도", "수치", "지명", "옛이름", "인명", "생물",
    "문헌기관", "개념어", "사물", "처분", "서술",
}
INDIVIDUAL_ATYPE = "개별보기_교차추출금지"
POOL_ATYPES = {
    "생물_조류", "생물_식물해조류", "생물_해양동물",
    "수치_길이_m", "연도_정수년", "지명_섬", "지명_지형",
    "문헌_자료명", "옛이름_섬",
}
VALID_ATYPES = BASE_ATYPES | POOL_ATYPES | {INDIVIDUAL_ATYPE}
LEGACY_ATYPES = {"탈것", "계절", "선박", "색"}
REQUIRED_BASE = (
    "id", "grade", "category", "q", "choices", "answer",
    "fact", "distractor", "explain", "atype", "rate",
)
REQUIRED_NEW = REQUIRED_BASE + ("src", "level")
VALID_LEVELS = {"L1", "L2", "L3", "L4", "L5", "L6"}
TEXT_FIELDS = (
    "grade", "category", "q", "fact", "distractor", "explain", "atype",
)
MARK = re.compile(r"[^\[\]]*\[\[([^\[\]]+)\]\][^\[\]]*", re.DOTALL)


def marked_value(fact: Any) -> str | None:
    if not isinstance(fact, str):
        return None
    match = MARK.fullmatch(fact)
    if match is None or not match.group(1).strip():
        return None
    return match.group(1).strip()


def load(path: str | Path) -> list:
    with open(path, encoding="utf-8-sig") as stream:
        data = json.load(stream)
    if isinstance(data, dict):
        if "questions" not in data:
            raise ValueError("루트 객체에 questions 필드가 필요합니다.")
        data = data["questions"]
    if not isinstance(data, list):
        raise ValueError("문항 데이터는 배열이어야 합니다.")
    return data


def validate(
    new_items: Any,
    existing_items: Any = None,
    strict_new: bool = True,
) -> bool:
    errs: list[str] = []
    warns: list[str] = []
    existing_items = [] if existing_items is None else existing_items
    if not isinstance(new_items, list) or not isinstance(existing_items, list):
        print("[오류] new_items와 existing_items는 배열이어야 합니다.")
        return False

    seen_ids: set[int] = set()
    seen_facts: set[str] = set()
    records: list[dict] = []

    # 기준 데이터도 타입을 검증한다. 잘못된 값으로 set/len 연산을 하지 않는다.
    for origin, items, is_new in (
        ("기존", existing_items, False),
        ("검사", new_items, strict_new),
    ):
        for index, q in enumerate(items):
            tag = f"[{origin}:{index}]"
            if not isinstance(q, dict):
                errs.append(f"{tag} 문항은 객체여야 합니다.")
                continue
            tag += f" id={q.get('id', '?')!r}"
            records.append(q)
            required = REQUIRED_NEW if is_new else REQUIRED_BASE
            for field in required:
                if field not in q:
                    errs.append(f"{tag} 필수 필드 누락: {field}")

            for field in TEXT_FIELDS:
                value = q.get(field)
                if not isinstance(value, str) or not value.strip():
                    errs.append(f"{tag} {field}는 비어 있지 않은 문자열이어야 합니다.")

            for field, allowed in (
                ("grade", VALID_GRADES), ("category", VALID_CATS),
            ):
                value = q.get(field)
                if not isinstance(value, str) or value not in allowed:
                    errs.append(f"{tag} {field} 오류: {value!r}")

            atype = q.get("atype")
            if isinstance(atype, str) and atype in LEGACY_ATYPES:
                (errs if is_new else warns).append(
                    f"{tag} 폐지 예정 atype: {atype}"
                )
            elif not isinstance(atype, str) or atype not in VALID_ATYPES:
                errs.append(f"{tag} atype 오류: {atype!r}")

            qid = q.get("id")
            if type(qid) is not int:
                errs.append(f"{tag} id는 bool/실수를 제외한 정수여야 합니다.")
            elif qid in seen_ids:
                errs.append(f"{tag} id 중복")
            else:
                seen_ids.add(qid)

            choices = q.get("choices")
            choices_ok = isinstance(choices, list)
            if not choices_ok:
                errs.append(f"{tag} choices는 문자열 배열이어야 합니다.")
            else:
                if len(choices) != 4:
                    errs.append(f"{tag} choices는 정확히 4개여야 합니다.")
                if not all(isinstance(c, str) and c.strip() for c in choices):
                    errs.append(f"{tag} choices의 각 값은 비어 있지 않은 문자열이어야 합니다.")
                elif len({c.strip() for c in choices}) != len(choices):
                    errs.append(f"{tag} choices에 중복 항목이 있습니다.")

            answer = q.get("answer")
            answer_ok = (
                type(answer) is int
                and choices_ok
                and 0 <= answer < len(choices)
            )
            if not answer_ok:
                errs.append(
                    f"{tag} answer는 bool/실수를 제외한 범위 내 정수 인덱스여야 합니다."
                )

            # 부재는 위에서 오류. 명시적 null은 유효한 값이다.
            if "rate" in q:
                rate = q["rate"]
                if rate is not None:
                    rate_ok = (
                        type(rate) in (int, float)
                        and (type(rate) is int or math.isfinite(rate))
                        and 0 <= rate <= 100
                    )
                    if not rate_ok:
                        errs.append(f"{tag} rate는 null 또는 0~100의 유한한 수여야 합니다.")
                    if is_new:
                        errs.append(f"{tag} 신규 문항의 rate는 반드시 null이어야 합니다.")

            if "level" in q:
                level = q["level"]
                if not isinstance(level, str) or level not in VALID_LEVELS:
                    errs.append(f"{tag} level은 L1~L6 중 하나여야 합니다.")

            fact = q.get("fact")
            val = marked_value(fact)

            # 개별 문항용 빈칸 보기를 다른 문항의 답으로 대체하지 않는다.
            blank = q.get("blankDistractors")
            need_blank = is_new and atype == INDIVIDUAL_ATYPE
            if need_blank and "blankDistractors" not in q:
                errs.append(f"{tag} 필수 필드 누락: blankDistractors")
            if "blankDistractors" in q:
                blank_ok = (
                    isinstance(blank, list)
                    and len(blank) == 3
                    and all(isinstance(v, str) and v.strip() for v in blank)
                )
                if not blank_ok:
                    errs.append(f"{tag} blankDistractors는 비어 있지 않은 문자열 3개의 배열이어야 합니다.")
                else:
                    normalized_blank = [v.strip() for v in blank]
                    if len(set(normalized_blank)) != 3:
                        errs.append(f"{tag} blankDistractors에 중복이 있습니다.")
                    if val is not None and val in normalized_blank:
                        errs.append(f"{tag} blankDistractors에 정답이 포함되어 있습니다.")
                    distractor_value = q.get("distractor")
                    if (
                        atype == INDIVIDUAL_ATYPE
                        and isinstance(distractor_value, str)
                        and distractor_value.strip() not in normalized_blank
                    ):
                        errs.append(f"{tag} distractor는 검수된 blankDistractors 중 하나여야 합니다.")

            # 자동으로 참/거짓이나 포함관계를 증명하는 검사는 아니다.
            if isinstance(fact, str) and isinstance(q.get("distractor"), str):
                ox_text = MARK.sub(
                    lambda m: m.group(0).replace("[[" + m.group(1) + "]]", q["distractor"]),
                    fact,
                )
                if re.search(r"약\s+약", ox_text):
                    (errs if is_new else warns).append(f"{tag} OX 치환 결과에 '약 약'이 있습니다.")
            if val is None:
                errs.append(f"{tag} fact에는 비어 있지 않은 [[ ]] 한 쌍이 필요합니다.")
            else:
                if not 2 <= len(val) <= 12:
                    warns.append(f"{tag} 마킹 값 {len(val)}자: 2~12자 권장")
                distractor = q.get("distractor")
                if isinstance(distractor, str):
                    if distractor.strip() == val:
                        errs.append(f"{tag} distractor가 정답과 동일합니다.")
                    if abs(len(distractor.strip()) - len(val)) > max(4, len(val)):
                        warns.append(f"{tag} distractor 길이 차이가 큽니다.")
                if atype == "수치_길이_m" and not re.fullmatch(
                    r"\d+(?:,\d{3})*(?:\.\d+)?m(?:\s*(?:미만|이하|초과|이상))?", val
                ):
                    errs.append(f"{tag} 수치_길이_m의 마킹 값은 m 단위 길이여야 합니다.")
                if atype == "연도_정수년" and not re.fullmatch(r"\d{1,4}년", val):
                    errs.append(f"{tag} 연도_정수년에는 단일 연도만 넣으세요.")

            if isinstance(fact, str) and fact.strip():
                normalized = " ".join(fact.split())
                if normalized in seen_facts:
                    errs.append(f"{tag} fact 중복")
                seen_facts.add(normalized)
                if not fact.rstrip().endswith("다."):
                    warns.append(f"{tag} fact가 '~다.'로 끝나지 않습니다.")

            wrong = q.get("wrong")
            if wrong is None:
                warns.append(f"{tag} wrong 누락")
            elif not isinstance(wrong, dict):
                errs.append(f"{tag} wrong은 객체여야 합니다.")
            else:
                allowed_keys = {str(i) for i in range(4)}
                for key, text in wrong.items():
                    if not isinstance(key, str) or key not in allowed_keys:
                        errs.append(f"{tag} wrong 키 오류: {key!r}")
                    if not isinstance(text, str) or not text.strip():
                        errs.append(f"{tag} wrong[{key!r}] 설명 오류")
                if answer_ok and str(answer) in wrong:
                    errs.append(f"{tag} wrong에 정답 인덱스가 들어 있습니다.")
                if answer_ok:
                    expected = allowed_keys - {str(answer)}
                    if set(wrong) != expected:
                        warns.append(f"{tag} wrong에는 오답 3개의 설명이 필요합니다.")

            src = q.get("src")
            if src is None or (isinstance(src, str) and not src.strip()):
                (errs if is_new else warns).append(f"{tag} src 없음")
            elif not isinstance(src, str):
                errs.append(f"{tag} src는 문자열이어야 합니다.")

            for field in ("deep", "tip"):
                value = q.get(field)
                if value is not None and not isinstance(value, str):
                    errs.append(f"{tag} {field}는 문자열 또는 null이어야 합니다.")
            if not isinstance(q.get("deep"), str) or not q["deep"].strip():
                warns.append(f"{tag} deep 누락")
            explain = q.get("explain")
            if isinstance(explain, str) and len(explain.strip()) < 25:
                warns.append(f"{tag} explain이 너무 짧습니다.")

            if q.get("asOf") is not None and type(q["asOf"]) is not int:
                errs.append(f"{tag} asOf는 정수 연도 또는 null이어야 합니다.")
            verify = q.get("verify")
            if verify is not None:
                if not isinstance(verify, list) or not all(
                    isinstance(url, str) and url.strip() for url in verify
                ):
                    errs.append(f"{tag} verify는 비어 있지 않은 문자열의 배열이어야 합니다.")
                elif len(verify) < 2:
                    warns.append(f"{tag} 확인 URL 2개 이상 권장")

    counts: Counter = Counter()
    distinct: dict[str, set[str]] = defaultdict(set)
    for q in records:
        atype = q.get("atype")
        if not isinstance(atype, str):
            continue
        counts[atype] += 1
        value = marked_value(q.get("fact"))
        if value is not None:
            distinct[atype].add(value)
    for atype in sorted(counts):
        if atype == INDIVIDUAL_ATYPE:
            warns.append(f"{atype}: 공유 풀 사용 금지; 출제기는 blankDistractors를 사용하고 없으면 원래 4지선다로 분기")
        elif atype != "서술" and counts[atype] < 3:
            warns.append(f"{atype}: 문항 {counts[atype]}개로 최소 3개 미달")
        if atype in POOL_ATYPES and len(distinct[atype]) < 4:
            warns.append(
                f"{atype}: 고유 정답 {len(distinct[atype])}개; "
                "4지선다용 공유 풀 부족, 개별보기로 대체"
            )

    print(f"검사 대상 {len(new_items)}문항 / 기준 데이터 {len(existing_items)}문항")
    print(f"오류 {len(errs)}건 / 경고 {len(warns)}건")
    for error in errs:
        print("  [오류]", error)
    for warning in warns:
        print("  [경고]", warning)
    for field in ("grade", "category", "atype"):
        distribution = Counter(
            q[field] for q in new_items
            if isinstance(q, dict) and isinstance(q.get(field), str)
        )
        print(f"{field} 분포:", dict(distribution))
    return not errs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="검사할 문항 JSON")
    parser.add_argument("existing", nargs="?", help="신규 배치의 기준 마스터 JSON")
    args = parser.parse_args()
    try:
        items = load(args.input)
        existing = load(args.existing) if args.existing is not None else None
    except (OSError, ValueError) as exc:
        print(f"[오류] 입력 파일을 읽을 수 없습니다: {exc}")
        return 2
    return 0 if validate(items, existing, strict_new=args.existing is not None) else 1


if __name__ == "__main__":
    raise SystemExit(main())