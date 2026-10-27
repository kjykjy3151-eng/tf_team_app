# 2026-10-27 16:12 KST
from pathlib import Path

import pytest

from tf.auth import User
from tf.roster import RosterError, parse_roster, reset_with_roster
from tf.rules import Student

ADMIN = User("admin", "관리자", True)
HEADER = "student_no,name,main_role,sub_roles\n"
REF = Path(__file__).resolve().parent.parent / "참고자료"


def _csv(body: str) -> bytes:
    return (HEADER + body).encode("utf-8-sig")


def test_parse_roster_reads_bom_and_sub_roles():
    rows = parse_roster(_csv("2026001,가나다,기획자,보고서 작성자\n2026002,라마바,웹 프로그래머,\n2026003,사아자,테스터,기획자;발표자\n"))
    assert rows == [
        Student("2026001", "가나다", "기획자", ("보고서 작성자",)),
        Student("2026002", "라마바", "웹 프로그래머", ()),
        Student("2026003", "사아자", "테스터", ("기획자", "발표자")),
    ]


def test_parse_roster_strips_spaces_and_blank_lines():
    rows = parse_roster(_csv(" 2026001 , 가나다 , 기획자 , 보고서 작성자 \n2026003,사아자,테스터,기획자 ; 발표자\n,,,\n\n"))
    assert rows == [
        Student("2026001", "가나다", "기획자", ("보고서 작성자",)),
        Student("2026003", "사아자", "테스터", ("기획자", "발표자")),
    ]


def test_parse_roster_rejects_unknown_role():
    with pytest.raises(RosterError, match="3행"):
        parse_roster(_csv("2026001,가나다,기획자,\n2026002,라마바,디자이너,\n"))


def test_parse_roster_rejects_three_sub_roles():
    with pytest.raises(RosterError, match="보조 역할"):
        parse_roster(_csv("2026001,가나다,기획자,테스터;발표자;보고서 작성자\n"))


def test_parse_roster_rejects_missing_column():
    with pytest.raises(RosterError, match="2행"):
        parse_roster(_csv("2026002,라마바,웹 프로그래머\n"))


def test_parse_roster_rejects_duplicate_and_admin_no():
    with pytest.raises(RosterError, match="겹침"):
        parse_roster(_csv("2026001,가나다,기획자,\n2026001,라마바,테스터,\n"))
    with pytest.raises(RosterError, match="admin"):
        parse_roster(_csv("admin,가나다,기획자,\n"))


def test_reset_clears_everything_and_makes_teams(conn):
    roster = parse_roster(_csv("2026001,가나다,기획자,\n2026002,라마바,테스터,\n"))
    reset_with_roster(conn, ADMIN, roster, 3)
    sid = conn.execute("select id from tf_students where student_no='2026001'").fetchone()[0]
    vid = conn.execute("select id from tf_students where student_no='2026002'").fetchone()[0]
    conn.execute("insert into tf_members (team_id, slot_no, student_id) values (1, 1, %s)", (sid,))
    app = conn.execute("insert into tf_applications (team_id, student_id, status) values (1, %s, '대기') returning id", (vid,)).fetchone()[0]
    conn.execute("insert into tf_votes (application_id, voter_id, vote) values (%s, %s, '찬성')", (app, sid))
    conn.execute("update tf_settings set value='true' where key='closed'")

    reset_with_roster(conn, ADMIN, roster, 4)

    count = lambda t: conn.execute(f"select count(*) from {t}").fetchone()[0]
    assert (count("tf_applications"), count("tf_votes"), count("tf_members")) == (0, 0, 0)
    assert [r[0] for r in conn.execute("select name from tf_teams order by id")] == ["팀1", "팀2", "팀3", "팀4"]
    assert conn.execute("select value from tf_settings where key='closed'").fetchone()[0] == "false"
    assert conn.execute("select count(*) from tf_students where not is_admin").fetchone()[0] == 2


@pytest.mark.parametrize("name,students,teams", [("쉬움 (1).csv", 8, 3), ("중간.csv", 12, 4), ("어려움.csv", 16, 4)])
def test_reset_with_practice_csv_files(conn, name, students, teams):
    roster = parse_roster((REF / name).read_bytes())
    assert len(roster) == students
    reset_with_roster(conn, ADMIN, roster, teams)
    assert conn.execute("select count(*) from tf_teams").fetchone()[0] == teams
    assert conn.execute("select count(*) from tf_students where not is_admin").fetchone()[0] == students


def test_parse_roster_rejects_main_role_in_sub_roles():
    with pytest.raises(RosterError, match="2행"):
        parse_roster(_csv("2026001,가나다,기획자,기획자;발표자\n"))
