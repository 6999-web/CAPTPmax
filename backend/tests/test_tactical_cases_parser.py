from main import _parse_tactical_cases


def test_parse_tactical_cases_supports_titles_with_quotes_and_spaces():
    lines = [
        "“6.30”贵溪级缉捕抢枪劫车案战术",
        "一、基本情况",
        "案例一材料第一段",
        "二、战斗经过",
        "案例一材料第二段",
        "“9. 10”阜阳级缉捕盗枪案战术",
        "一、基本情况",
        "案例二材料第一段",
        "三、战斗经过",
        "案例二材料第二段",
    ]

    cases = _parse_tactical_cases(lines)

    assert [case["title"] for case in cases] == [
        "6.30贵溪级缉捕抢枪劫车案战术",
        "9.10阜阳级缉捕盗枪案战术",
    ]
    assert len(cases[0]["questions"]) == 4
    assert "案例一材料第一段" in cases[0]["material"]
    assert "案例二材料第一段" in cases[1]["material"]
