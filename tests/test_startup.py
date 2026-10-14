"""Real server startup from a Unicode/space path, including occupied port fallback."""
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import requests

class StartupTests(unittest.TestCase):
    def test_unicode_cwd_and_occupied_port(self):
        source=Path(__file__).resolve().parents[1]
        blocker=socket.socket()
        try:
            try: blocker.bind(('127.0.0.1',8765));blocker.listen(1)
            except OSError: blocker.close()  # An existing local server already occupies it.
            with tempfile.TemporaryDirectory(prefix='안전 폴더 ') as directory:
                root=Path(directory)/'1028FALL STUDIO'
                shutil.copytree(source,root,ignore=shutil.ignore_patterns('.venv','.git','data','__pycache__','.env'))
                process=subprocess.Popen([sys.executable,str(root/'app.py'),'--no-browser'],cwd=root,
                                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                try:
                    line=process.stdout.readline()
                    match=re.search(r'http://127.0.0.1:(\d+)',line)
                    self.assertIsNotNone(match,line)
                    self.assertGreaterEqual(int(match.group(1)),8766)
                    address=match.group(0)
                    for attempt in range(20):
                        try:
                            response=requests.get(address,timeout=2)
                            break
                        except requests.ConnectionError:
                            time.sleep(.05)
                    else: self.fail('Server did not become ready')
                    self.assertEqual(response.status_code,200)
                    self.assertIn('1028FALL',response.text)
                    session=requests.Session()
                    self.assertEqual(session.get(address,timeout=2).status_code,200)
                    response=session.get(address+'/api/state',timeout=2)
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(response.json()['items'],[])
                finally:
                    process.terminate()
                    process.wait(timeout=5)
                    process.stdout.close();process.stderr.close()
        finally:
            blocker.close()

    def test_production_session_key_preserves_work_after_process_restart(self):
        import io
        from PIL import Image
        source=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='재시작 테스트 ') as directory:
            root=Path(directory)/'1028FALL STUDIO'
            shutil.copytree(source,root,ignore=shutil.ignore_patterns('.venv','.git','data','__pycache__','.env'))
            def launch():
                process=subprocess.Popen([sys.executable,str(root/'app.py'),'--no-browser'],cwd=root,
                                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                match=re.search(r'http://127.0.0.1:\d+',process.stdout.readline())
                if not match:
                    process.terminate();process.wait(timeout=5)
                    self.fail('Server startup failed')
                return process,match.group(0)
            def stop(process):
                process.terminate();process.wait(timeout=5);process.stdout.close();process.stderr.close()
            client=requests.Session()
            first,address=launch()
            try:
                html=client.get(address,timeout=3)
                token=re.search(r'name="studio-token" content="([a-f0-9]+)"',html.text).group(1)
                headers={'X-Studio-Token':token}
                image=io.BytesIO();Image.new('RGB',(100,80)).save(image,'PNG')
                response=client.post(address+'/api/v2/sets/A/sources',headers=headers,files={'files':('source.png',image.getvalue(),'image/png')},timeout=3)
                self.assertEqual(response.status_code,200)
                client.post(address+'/api/v2/sets/A/versions/ko',json={},headers=headers,timeout=3)
                client.patch(address+'/api/v2/sets/A/versions/ko',json={'hook':'재시작 후 보존','caption':'보존된 본문'},headers=headers,timeout=3)
                before=client.get(address+'/api/v2/project',timeout=3).json()['project']
            finally:stop(first)
            second,next_address=launch()
            try:
                self.assertEqual(address,next_address)
                response=client.get(next_address+'/api/v2/project',timeout=3)
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json()['project'],before)
                self.assertEqual(response.json()['project']['sets']['A']['versions']['ko']['hook'],'재시작 후 보존')
            finally:stop(second);client.close()
