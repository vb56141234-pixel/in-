"""Python side of Windows launchers; paths stay Unicode and no shell is used."""
import getpass
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent

def setup_key():
    from dotenv import set_key
    print('1028FALL Studio API 키 설정 (입력은 화면에 표시되지 않습니다)')
    key=getpass.getpass('OpenAI API 키: ').strip()
    if not key:
        print('입력이 없어 기존 설정을 유지합니다.'); return
    if not key.startswith('sk-') or any(ch.isspace() for ch in key):
        raise ValueError('OpenAI API 키 형식을 확인하세요.')
    set_key(str(ROOT/'.env'),'OPENAI_API_KEY',key)
    print('로컬 .env에 저장했습니다. 실행 중인 앱을 종료 후 다시 실행하세요.')

if __name__=='__main__':
    try:
        if '--setup-key' in sys.argv:
            setup_key()
        else:
            from app import main
            main()
    except KeyboardInterrupt:
        print('\n종료했습니다.')
    except Exception as exc:
        print(f'실행 실패: {exc}',file=sys.stderr)
        sys.exit(1)
