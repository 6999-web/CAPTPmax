from main import _parse_tactical_cases


def test_parse_tactical_cases_supports_titles_with_quotes_and_spaces():
    lines = [
        "“6.30”贵溪缉捕抢枪劫车案犯战斗",
        "一、基本情况",
        "案例一材料第一段",
        "二、战斗经过",
        "案例一材料第二段",
        "“9.10”阜阳缉捕盗枪案战斗",
        "一、基本情况",
        "案例二材料第一段",
        "二、战斗经过",
        "案例二材料第二段",
    ]

    cases = _parse_tactical_cases(lines)

    assert [case["title"] for case in cases] == [
        "6.30贵溪缉捕抢枪劫车案犯战斗",
        "9.10阜阳缉捕盗枪案战斗",
    ]
    assert len(cases[0]["questions"]) == 4
    assert cases[0]["material"] == "2.mp4"
    assert cases[0]["mediaType"] == "video"
    assert cases[0]["mediaUrl"] == "/api/tactical-media/2.mp4"
    assert cases[1]["material"] == "4.mp4"
    assert cases[1]["mediaType"] == "video"
    assert cases[1]["mediaUrl"] == "/api/tactical-media/4.mp4"


def test_parse_tactical_cases_hides_removed_case_pages():
    lines = [
        "3.21竹山缉捕特大报复案战斗",
        "案例一材料第一段",
        "10.27缉捕盗枪杀人案犯战斗",
        "案例二材料第一段",
        "1.29守候缉捕重大犯罪团伙战斗",
        "案例三材料第一段",
        "6.30贵溪缉捕抢枪劫车案犯战斗",
        "案例四材料第一段",
    ]

    cases = _parse_tactical_cases(lines)
    titles = [case["title"] for case in cases]

    assert "10.27缉捕盗枪杀人案犯战斗" not in titles
    assert "1.29守候缉捕重大犯罪团伙战斗" not in titles
    assert "3.21竹山缉捕特大报复案战斗" in titles
    assert "6.30贵溪缉捕抢枪劫车案犯战斗" in titles
