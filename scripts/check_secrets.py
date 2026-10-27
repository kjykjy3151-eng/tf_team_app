# 2026-10-27 16:08 KST
"""커밋 전에 .env의 비밀 값이 커밋 대상 파일에 들어 있는지 검사한다.

값은 출력하지 않고 "비밀값: 없음" 또는 "비밀값: 있음(파일 이름)"만 출력한다.
"""
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
NAMES = ("OPENROUTER_API_KEY", "DATABASE_URL", "ADMIN_PASSWORD")


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def main() -> int:
    env = dotenv_values(ROOT / ".env")
    secrets = [env[n].encode() for n in NAMES if env.get(n)]
    tracked = [p for p in git("ls-files", "--cached", "-z").decode().split("\0") if p]
    found = [p for p in tracked if Path(p).name == ".env"]
    for path in tracked:
        blob = git("show", f":{path}")  # 커밋될 내용(스테이징된 내용)을 읽는다.
        if any(s in blob for s in secrets):
            found.append(path)
    if found:
        print(f"비밀값: 있음({', '.join(sorted(set(found)))})")
        return 1
    print("비밀값: 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
