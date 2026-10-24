from pathlib import Path
import json,os,subprocess,time,sys
variant=sys.argv[1]
assert variant in ('feature','yield')
root=Path('/tmp/bim3117-v050-catalog')/('native-'+variant);root.mkdir(exist_ok=True)
output=root/'evidence';output.mkdir(exist_ok=True)
assets=Path('/tmp/bim3117-freecad')
env=dict(os.environ)
for name in ('PYTHONHOME','PYTHONPATH','FREECAD_USER_HOME','FREECAD_USER_DATA','FREECAD_USER_TEMP'):env.pop(name,None)
for name,child in (('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache')):env[name]=str(root/child)
env.update(DISPLAY=':119',QTWEBENGINE_DISABLE_SANDBOX='1',LIBGL_ALWAYS_SOFTWARE='1',FONTCONFIG_FILE='/etc/fonts/fonts.conf',FONTCONFIG_PATH='/etc/fonts')
runtime=assets/'squashfs-root/AppRun'
macro=root/'native.FCMacro'
macro.write_text("import sys,traceback\nfrom PySide import QtCore,QtWidgets\nsys.path.insert(0,'/tmp/bim3117-v050-catalog')\nfrom probe_variants import start\nQtCore.QTimer.singleShot(1500,lambda:start("+repr(str(output))+","+repr(variant)+"))\n")
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
   try:code=process.wait(timeout=45)
   except subprocess.TimeoutExpired:process.terminate();code=124
 finally:
  x.terminate()
  try:x.wait(timeout=5)
  except subprocess.TimeoutExpired:x.kill()
summary={'exit_code':code,'report':str(output/'report.json'),'log':str(output/'gui.log')}
(output/'external-outcome.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary));print((output/'gui.log').read_text()[-6000:])
