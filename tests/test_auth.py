# 2026-10-27 16:12 KST
import pytest

from tf.auth import User, ensure_admin, login
from tf.roster import parse_roster, reset_with_roster

ADMIN = User("admin", "관리자", True)
CSV = (
    "student_no,name,main_role,sub_roles\n"
    "2026001,가나다,기획자,보고서 작성자\n"
    "2026002,라마바,웹 프로그래머,\n"
    "2026003,사아자,테스터,기획자;발표자\n"
).encode("utf-8-sig")


@pytest.fixture
def loaded(conn):
    reset_with_roster(conn, ADMIN, parse_roster(CSV), 3)
    return conn


def test_password_is_hashed_not_plain(loaded):
    hashes = [r[0] for r in loaded.execute("select password_hash from tf_students where not is_admin")]
    assert len(hashes) == 3
    assert all(h != "1234" and h.startswith("$2") for h in hashes)


def test_login_ok_with_1234(loaded):
    user = login(loaded, "2026001", "1234")
    assert user == User("2026001", "가나다", False)


def test_login_trims_student_no(loaded):
    assert login(loaded, " 2026001 ", "1234") is not None


def test_login_fails_with_wrong_or_empty_password(loaded):
    assert login(loaded, "2026001", "12345") is None
    assert login(loaded, "2026001", "") is None


def test_login_fails_for_unknown_student(loaded):
    assert login(loaded, "9999999", "1234") is None


def test_admin_created_and_password_updated(conn):
    ensure_admin(conn, "a1")
    assert login(conn, "admin", "a1") == User("admin", "관리자", True)
    ensure_admin(conn, "b2")
    assert login(conn, "admin", "a1") is None
    assert login(conn, "admin", "b2") is not None


def test_admin_survives_roster_reset(conn):
    ensure_admin(conn, "a1")
    reset_with_roster(conn, ADMIN, parse_roster(CSV), 3)
    reset_with_roster(conn, ADMIN, parse_roster(CSV), 4)
    assert login(conn, "admin", "a1") is not None


def test_student_cannot_reset(conn):
    with pytest.raises(PermissionError):
        reset_with_roster(conn, User("2026001", "가나다", False), parse_roster(CSV), 3)
