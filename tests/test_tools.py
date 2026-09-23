import json,os,pathlib,subprocess,sys,tempfile,time,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from codex_limit_tools.common import connect,get,put
from codex_limit_tools.usage import index,aggregate,load_prices
from codex_limit_tools.estimate import estimate,report
from codex_limit_tools.tracker import Collector,running
from codex_limit_tools.tui import lines_for
from codex_limit_tools.quota import QuotaSource
ROOT=pathlib.Path(__file__).resolve().parents[1]

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.home=self.root/'codex';(self.home/'sessions').mkdir(parents=True)
  self.db=connect(self.root/'state');self.prices=load_prices(ROOT/'prices.json')
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def log(self,name='a',thread='owner',model='gpt-6-sol',rid='r1',owner=None,ts=None,inp=100000,cached=50000,out=1000):
  entries=[{'type':'session_meta','payload':{'id':thread}}, {'type':'turn_context','payload':{'turn_id':'turn','model':model}},
           {'type':'token_usage_record','timestamp':ts or time.time(),'payload':{'response_id':rid,'thread_id':owner or thread,'turn_id':'turn','usage':{'input_tokens':inp,'cached_input_tokens':cached,'output_tokens':out,'reasoning_output_tokens':100}}}]
  p=self.home/'sessions'/('rollout-'+name+'.jsonl');p.write_text(''.join(json.dumps(e)+'\n' for e in entries));return p
 def test_sol_pricing_no_double_counts(self):
  self.log();index(self.db,self.home);m=aggregate(self.db,self.prices)
  self.assertEqual(m['input'],100000);self.assertEqual(m['output'],1000)
  self.assertAlmostEqual(m['cost'],.12);self.assertEqual(m['reasoning'],100)
 def test_foreign_before_original_and_duplicate(self):
  self.log('a',thread='fork',owner='owner');self.log('b');self.log('c')
  stats=index(self.db,self.home)
  self.assertEqual(stats['foreign'],1);self.assertEqual(stats['duplicates'],1)
  self.assertEqual(aggregate(self.db,self.prices)['responses'],1)
 def test_incremental_partial_line(self):
  p=self.log();index(self.db,self.home);self.assertEqual(index(self.db,self.home)['changed_files'],0)
  e={'type':'token_usage_record','timestamp':time.time(),'payload':{'thread_id':'owner','turn_id':'turn','response_id':'r2','usage':{'input_tokens':10}}}
  with p.open('a') as f:f.write(json.dumps(e))
  index(self.db,self.home);self.assertEqual(aggregate(self.db,self.prices)['responses'],1)
  with p.open('a') as f:f.write('\n')
  index(self.db,self.home);self.assertEqual(aggregate(self.db,self.prices)['responses'],2)
 def test_unpriced_retained(self):
  self.log(model='internal-agent');index(self.db,self.home);m=aggregate(self.db,self.prices)
  self.assertEqual(m['unpriced_tokens'],101000);self.assertEqual(m['cost'],0)
 def test_unknown_dated_suffix(self):
  self.log(model='gpt-6-sol-internal');index(self.db,self.home)
  self.assertEqual(aggregate(self.db,self.prices)['unpriced_tokens'],101000)
 def test_long_context(self):
  self.log(inp=300000,cached=100000,out=2000);index(self.db,self.home)
  self.assertAlmostEqual(aggregate(self.db,self.prices)['cost'],.8+.04+.03)
 def test_truncation_deduplicates(self):
  p=self.log();index(self.db,self.home);p.write_text(p.read_text());index(self.db,self.home)
  self.assertEqual(aggregate(self.db,self.prices)['responses'],1)
 def test_invalid_counters_rejected(self):
  self.log(inp=100,cached=200);stats=index(self.db,self.home)
  self.assertEqual(stats['invalid'],1);self.assertEqual(aggregate(self.db,self.prices)['responses'],0)
 def test_other_home_rejected(self):
  index(self.db,self.home)
  with self.assertRaises(ValueError):index(self.db,self.root/'another')
 def test_ratio_and_rounding(self):
  a={'ts':0,'used':10,'metrics':{'cost':0,'input':0,'output':0,'models':{}}}
  b={'ts':300,'used':20,'metrics':{'cost':40,'input':1000,'output':0,'priced_tokens':1000,'models':{}}}
  r=estimate(a,b);self.assertEqual(r['estimate']['cost'],400)
  self.assertAlmostEqual(r['cost_rounding_range'][0],4000/11)
  self.assertAlmostEqual(r['cost_rounding_range'][1],4000/9)
  b['used']=10;self.assertIsNone(estimate(a,b)['estimate'])
 def test_no_activity_no_estimate(self):
  a={'ts':0,'used':10,'metrics':{}};b={'ts':300,'used':20,'metrics':{}}
  self.assertIsNone(estimate(a,b)['estimate'])
 def test_reset_and_pause_segments(self):
  now=time.time();self.log(ts=now)
  c={'prices':self.prices,'codex_home':str(self.home),'started_at':now-100,'interval':300,'resolution':1,'min_points':5,'label':'test','codex_bin':'unused','bucket':'codex'}
  samples=[{'used':10,'left':90,'reset_at':now+10000,'account':'same','plan':'pro','at':now+1},
           {'used':1,'left':99,'reset_at':now+20000,'account':'same','plan':'pro','at':now+2}]
  class Fake:
   def read(inner):return samples.pop(0)
  t=Collector(self.db,c,Fake());t.collect();t.collect()
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM segments').fetchone()[0],2)
  t.boundary('pause');self.assertIsNone(t.segment)
 def test_midnight_collection_continues(self):
  from analysis_fixtures import MIDNIGHT
  self.log(ts=86000)
  c={'prices':self.prices,'codex_home':str(self.home),'started_at':85000,'interval':300,'resolution':1,'min_points':5,'label':'test','codex_bin':'unused','bucket':'codex'}
  samples=[{'used':s['used'],'left':100-s['used'],'reset_at':9999999999,'account':'synthetic','plan':'pro','at':s['ts']} for s in MIDNIGHT]
  class Fake:
   def read(inner):return samples.pop(0)
  t=Collector(self.db,c,Fake())
  with patch('codex_limit_tools.tracker.aggregate',side_effect=[s['metrics'] for s in MIDNIGHT]):
   for s in MIDNIGHT:
    with patch('codex_limit_tools.tracker.time.time',return_value=s['ts']):t.collect()
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM segments').fetchone()[0],1)
  data=report(self.db,{})
  self.assertEqual(data['segments'][0]['delta']['cost'],8)
  self.assertEqual(data['daily'][0]['day'],'1970-01-02')
  self.assertEqual(data['daily'][0]['points'],2)
 def test_prices_json_validation(self):
  data=dict(self.prices);data['long_input_multiplier']=-1;p=self.root/'bad.json';p.write_text(json.dumps(data))
  with self.assertRaises(ValueError):load_prices(p)
 def test_tui_render(self):
  rows=lines_for({'phase':'tracking','left':56},None,[],{'interval':300},100)
  self.assertTrue(any('56%' in text for text,_ in rows))
 def test_fake_rpc_allowlist(self):
  fake=self.root/'fake-codex';audit=self.root/'audit';fake.write_text('''#!/usr/bin/env python3
import json,sys,os
assert sys.argv[1:]==['app-server']
for line in sys.stdin:
 m=json.loads(line)
 with open(__file__+'.audit','a') as f:f.write(m['method']+'\\n')
 assert m['method'] in ['initialize','initialized','account/read','account/rateLimits/read']
 if m['method']=='initialized':continue
 if m['method']=='account/read' and os.path.exists(__file__+'.fail'):
  print(json.dumps({'id':m['id'],'error':{'code':-1}}),flush=True);continue
 if m['method']=='account/read':result={'account':{'type':'chatgpt','email':'fake@example.invalid','planType':'pro'}}
 elif m['method']=='account/rateLimits/read':result={'rateLimits':{'limitId':'codex','primary':{'usedPercent':44,'windowDurationMins':10080,'resetsAt':9999999999},'secondary':None}}
 else:result={}
 print(json.dumps({'id':m['id'],'result':result}),flush=True)
''');fake.chmod(0o755)
  source=QuotaSource(str(fake))
  try:self.assertEqual(source.read()['left'],56)
  finally:source.close()
  self.assertEqual(pathlib.Path(str(fake)+'.audit').read_text().splitlines(),['initialize','initialized','account/read','account/rateLimits/read'])
  self.log()
  state=self.root/'live-state'
  cmd=[sys.executable,str(ROOT/'codex-limit-estimator')]
  result=subprocess.run(cmd+['start','tracking','--background','--data-dir',str(state),'--codex-home',str(self.home),'--codex-bin',str(fake)],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr)
  live=connect(state)
  def wait_phase(phase):
   deadline=time.monotonic()+5
   while time.monotonic()<deadline:
    if get(live,'status',{}).get('phase')==phase:return
    time.sleep(.05)
   self.fail('Expected phase '+phase+'; got '+str(get(live,'status')))
  try:
   wait_phase('tracking');self.assertTrue(running(state))
   count=live.execute('SELECT count(*) FROM snapshots').fetchone()[0]
   checkpoint=subprocess.run(cmd+['checkpoint','--wait','--json','--timeout','3','--data-dir',str(state)],capture_output=True,text=True,timeout=5)
   self.assertEqual(checkpoint.returncode,0,checkpoint.stderr)
   acknowledgement=json.loads(checkpoint.stdout)
   self.assertEqual(acknowledgement['status'],'complete')
   self.assertEqual(live.execute('SELECT count(*) FROM snapshots').fetchone()[0],count+1)
   self.assertEqual(acknowledgement['snapshot_id'],get(live,'status')['snapshot_id'])
   inspected=subprocess.run(cmd+['checkpoint','--request-id',acknowledgement['id'],'--json','--data-dir',str(state)],capture_output=True,text=True,check=True)
   self.assertEqual(json.loads(inspected.stdout),acknowledgement)
   # Exercise curses with a real pseudoterminal. q must leave collection running.
   import pty,fcntl,termios,struct
   master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',40,110,0,0))
   env=os.environ.copy();env['TERM']='xterm-256color'
   ui=subprocess.Popen(cmd+['--data-dir',str(state)],stdin=slave,stdout=slave,stderr=slave,env=env)
   os.close(slave)
   try:
    time.sleep(.3);os.write(master,b'q');ui.wait(timeout=5)
    self.assertEqual(ui.returncode,0);self.assertTrue(running(state))
   finally:
    if ui.poll() is None:ui.kill();ui.wait()
    os.close(master)
   subprocess.run(cmd+['stop','--data-dir',str(state)],capture_output=True,check=True);wait_phase('paused')
   rejected=subprocess.run(cmd+['checkpoint','--wait','--data-dir',str(state)],capture_output=True,text=True)
   self.assertNotEqual(rejected.returncode,0)
   self.assertIn('paused',rejected.stderr)
   self.assertTrue(get(live,'control')['paused'])
   subprocess.run(cmd+['resume','--data-dir',str(state)],capture_output=True,check=True);wait_phase('tracking')
   pathlib.Path(str(fake)+'.fail').write_text('synthetic failure')
   failed=subprocess.run(cmd+['checkpoint','--wait','--timeout','3','--data-dir',str(state)],capture_output=True,text=True,timeout=5)
   self.assertNotEqual(failed.returncode,0)
   self.assertIn('failed',failed.stderr)
   self.assertIn('RPC account/read',failed.stderr)
  finally:
   subprocess.run(cmd+['shutdown','--data-dir',str(state)],capture_output=True)
   deadline=time.monotonic()+5
   while running(state) and time.monotonic()<deadline:time.sleep(.05)
   live.close()
  self.assertFalse(running(state))


if __name__=='__main__':unittest.main()
