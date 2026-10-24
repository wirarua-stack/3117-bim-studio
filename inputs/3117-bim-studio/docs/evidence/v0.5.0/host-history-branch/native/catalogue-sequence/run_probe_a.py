from pathlib import Path
import json,os,subprocess,time
root=Path('/tmp/bim3117-v050-catalog');output=root/'probe-a';output.mkdir(exist_ok=True)
assets=Path('/tmp/bim3117-freecad');repo=Path('/workspace/scratch/9457befac3c8/3117-bim-studio')
env=dict(os.environ)
for name in ('PYTHONHOME','PYTHONPATH','FREECAD_USER_HOME','FREECAD_USER_DATA','FREECAD_USER_TEMP'):env.pop(name,None)
for name,child in (('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache')):env[name]=str(root/child)
env.update(DISPLAY=':119',QTWEBENGINE_DISABLE_SANDBOX='1',LIBGL_ALWAYS_SOFTWARE='1',FONTCONFIG_FILE='/etc/fonts/fonts.conf',FONTCONFIG_PATH='/etc/fonts')
runtime=assets/'squashfs-root/AppRun'
installenv=dict(env,BIM3117_QA_STAGE='install',BIM3117_QA_OUTPUT=str(output),QT_QPA_PLATFORM='offscreen')
r=subprocess.run([str(runtime),'freecadcmd','-u',str(root/'user.cfg'),str(repo/'tests/run_freecad_tests.py')],env=installenv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
(output/'install.log').write_bytes(r.stdout)
macro=root/'run_probe_a.FCMacro'
macro.write_text("""import sys,traceback
from PySide import QtCore,QtWidgets
sys.path.insert(0,'/workspace/scratch/9457befac3c8/3117-bim-studio/tests')
sys.path.insert(0,'/tmp/bim3117-v050-catalog')
def run_tests():
 try:
  from probe_a import run
  print(run('/tmp/bim3117-v050-catalog/probe-a')['status'],flush=True)
 except BaseException:traceback.print_exc()
 QtCore.QTimer.singleShot(150,QtWidgets.QApplication.quit)
QtCore.QTimer.singleShot(1500,run_tests)
""")
xenv=dict(env);xenv['LD_LIBRARY_PATH']=str(assets/'xvfb/root/usr/lib/x86_64-linux-gnu')+':'+str(assets/'squashfs-root/usr/lib');xenv['XKB_BINDIR']=str(assets/'xvfb/root/usr/bin')
with (output/'xvfb.log').open('w') as log:
 x=subprocess.Popen([str(assets/'xvfb/root/usr/bin/Xvfb'),':119','-screen','0','1600x1100x24','-nolisten','tcp','-noreset','-ac'],env=xenv,stdout=log,stderr=subprocess.STDOUT)
 try:
  for _ in range(50):
   if x.poll() is not None:raise RuntimeError((output/'xvfb.log').read_text())
   if Path('/tmp/.X11-unix/X119').exists():break
   time.sleep(.1)
  with (output/'gui.log').open('w') as glog:
   process=subprocess.Popen([str(runtime),'-u',str(root/'user.cfg'),str(macro)],env=env,stdin=subprocess.DEVNULL,stdout=glog,stderr=subprocess.STDOUT)
   try:code=process.wait(timeout=120)
   except subprocess.TimeoutExpired:process.terminate();code=124
 finally:
  x.terminate()
  try:x.wait(timeout=5)
  except subprocess.TimeoutExpired:x.kill()
print(json.dumps({'exit_code':code,'report':str(output/'probe-a-report.json')}))
print((output/'gui.log').read_text()[-6000:])
