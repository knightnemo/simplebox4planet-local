"""Start/stop the local app without depending on the editor's terminal lifetime."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:8766'
RUNTIME=ROOT/'runtime';RUNTIME.mkdir(exist_ok=True)
PID=RUNTIME/'server.pid'
def health():
    try:
        with urllib.request.urlopen(URL+'/api/health',timeout=1) as response:
            return json.load(response).get('frontend')=='studio'
    except Exception:return False
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stop',action='store_true');parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    if args.stop:
        if not PID.exists():print('没有本启动器记录的后台进程。');return
        pid=int(PID.read_text());cmd=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True).stdout
        if str(ROOT/'server.py') in cmd:
            os.kill(pid,signal.SIGTERM);PID.unlink(missing_ok=True);print('本地网页已停止。')
        else:print('记录的进程已退出，不会终止其他进程。')
        return
    if not health():
        with open(RUNTIME/'server.log','ab') as log:
            p=subprocess.Popen([sys.executable,str(ROOT/'server.py')],cwd=ROOT,stdout=log,stderr=log,start_new_session=True)
        PID.write_text(str(p.pid))
        for _ in range(30):
            if health():break
            if p.poll() is not None:raise SystemExit('启动失败，请查看 runtime/server.log（可能端口已被占用）。')
            time.sleep(.3)
        else:raise SystemExit('启动超时，请查看 runtime/server.log。')
    print('本地网页已运行：'+URL)
    if not args.no_browser:webbrowser.open(URL)
if __name__=='__main__':main()
