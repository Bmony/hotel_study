#!/usr/bin/env python3
"""
enriched_hotels.json 파일 변경 감지 및 자동 재인덱싱
"""

import time
import os
import subprocess
from pathlib import Path
from datetime import datetime


class AutoReindexWatcher:
    def __init__(self, watch_file: str, check_interval: int = 5):
        """
        Args:
            watch_file: 감시할 파일 경로
            check_interval: 체크 주기 (초)
        """
        self.watch_file = Path(watch_file)
        self.check_interval = check_interval
        self.last_modified = None
        self.indexer_script = Path(__file__).parent / "elasticsearch_indexer.py"

    def get_file_modified_time(self):
        """파일 수정 시간 가져오기"""
        if self.watch_file.exists():
            return os.path.getmtime(self.watch_file)
        return None

    def reindex(self):
        """재인덱싱 실행"""
        print(f"\n{'='*60}")
        print(f"🔄 재인덱싱 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        try:
            result = subprocess.run(
                ['python3', str(self.indexer_script)],
                cwd=self.indexer_script.parent,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                print("✅ 재인덱싱 성공!")
                print(result.stdout)
            else:
                print("❌ 재인덱싱 실패!")
                print(result.stderr)

        except subprocess.TimeoutExpired:
            print("⏱️ 재인덱싱 타임아웃 (5분 초과)")
        except Exception as e:
            print(f"❌ 에러: {e}")

        print(f"{'='*60}\n")

    def watch(self):
        """파일 변경 감지 및 자동 재인덱싱"""
        print(f"👀 파일 감시 시작: {self.watch_file}")
        print(f"   체크 주기: {self.check_interval}초")
        print(f"   Ctrl+C로 중지\n")

        # 초기 수정 시간 저장
        self.last_modified = self.get_file_modified_time()

        try:
            while True:
                current_modified = self.get_file_modified_time()

                # 파일이 수정되었는지 확인
                if current_modified and current_modified != self.last_modified:
                    if self.last_modified is not None:  # 초기 실행이 아닐 때만
                        print(f"📝 파일 변경 감지!")
                        self.reindex()

                    self.last_modified = current_modified

                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            print("\n\n⏹️  파일 감시 중지")


def main():
    # enriched_hotels.json 경로
    project_root = Path(__file__).parent.parent.parent
    enriched_file = project_root / "data" / "processed" / "enriched_hotels.json"

    if not enriched_file.exists():
        print(f"❌ 파일을 찾을 수 없습니다: {enriched_file}")
        return

    watcher = AutoReindexWatcher(watch_file=enriched_file, check_interval=5)
    watcher.watch()


if __name__ == '__main__':
    main()
