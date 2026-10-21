"""RPF-60 bounded projection, persistent one-session Gateway and free preflight CLI.

Transport reuses the existing Origin/Bearer boundary. Never resumes execution.
"""
import copy,hashlib,os,re,secrets,socket,threading,time,uuid
from pathlib import Path
from . import lab_cross_domain_contracts as c,lab_cross_domain as core,lab_cross_domain_verify as v
from .lab_store import LabError
SCHEMA='rpf60-cross-domain-lab-v1'
REVIEWED_SHA='0bb359ca78c7c0415afef30ff959d41112da3f5155e5ae18e68be28735f9996a'
TERMINAL={'COMPLETED','CANCELLED','RECONCILE_REQUIRED','INCONCLUSIVE','PLATFORM_ERROR'}

def projection(payload,source,anchor,size,verdict):
    rows=[]
    for row in payload['rows']:
        contract,e=row['contract'],row['evidence'];domain=contract['experiment']['domain']
        if domain==c.DOMAINS[0]:
            before=e['before']['data'];after=e['after']['data'];a=before['order'];b=after['order']
            diff={k:{'before':a[k],'after':b[k]} for k in ('status','refunded_minor','revision')}
            cleanup=e['cleanup'];fault=e['fault']
        else:
            scene=e['scene'];before={'state':'ABSENT'};after={'value':'rpf53-v2','version':2,'history':[2,1]}
            diff={k:{'before':before.get(k,'ABSENT'),'after':val} for k,val in after.items()}
            cleanup=scene['environment']['cleanup'];fault=scene['fault']
        rows.append({'round':row['round'],'candidate_id':row['candidate_id'],'run_id':contract['experiment']['run_id'],
            'target_source':c.BOUNDARIES['target_sources'][domain],'authority':row['feedback']['authority'],
            'tool_call_id':row['selection']['id'],'response_id':row['observation']['shape']['response_id'],
            'request_sha256':c.digest(row['body']),'input':row['input'],'feedback':row['feedback'],
            'feedback_sha256':c.digest(row['feedback']),'status':'CONTRACT_SATISFIED_IN_RUN','before':before,'after':after,
            'state_diff':diff,'fault':fault,'fault_status':'NOT_TRIGGERED','cleanup':cleanup})
    return {'schema_version':SCHEMA,'session_id':payload['plan']['session_id'],'source':source,'status':'COMPLETED',
        'rows':rows,'events':[{'seq':e['seq'],'event_id':'e'+str(e['seq']),'type':e['kind'],'monotonic_ns':e['monotonic_ns'],
            'round':e['data'].get('round'),'domain':e['data'].get('domain')} for e in payload['ledger_chain'][-1]['state']['events']],
        'witness':{'status':'OFFLINE_VERIFIER_PASS','sha256':anchor,'bytes':size,'verifier':verdict.get('verifier_identity',{}),
            'issuer_authenticity':'NOT_ESTABLISHED','provenance':'LOCAL_CONTENT_AND_SOURCE_CHECKED'},
        'usage':verdict['actual'],'reserved_budget':verdict['reserved_budget'],'research':verdict['research'],
        'boundaries':payload['boundaries'],'source_sha256':c.digest(payload['plan']['source_files']),
        'rationale':'RATIONALE_NOT_RECORDED','cancel_requested':False,'error_code':None}

def reviewed():
    from . import pge_select_verify as original
    raw=(c.ROOT/'spikes/rpf-59/cross-domain-selection-evidence.json').read_bytes()
    c.require(len(raw)<=1500000 and hashlib.sha256(raw).hexdigest()==REVIEWED_SHA,'REVIEWED_RAW_ANCHOR')
    verdict=original.verify_bytes(raw,REVIEWED_SHA);verdict['verifier_identity']=original.identity()
    return projection(c.strict_json(raw)['payload'],'REVIEWED',REVIEWED_SHA,len(raw),verdict)

class CrossDomainStore:
    """One durable task quota; request recovery is read-only, restart never runs work."""
    def __init__(self,*,enabled=False,root=None,runner=None):
        self.root=c.scoped(root or c.WORK/'gateway');self.root.mkdir(parents=True,exist_ok=True)
        self.enabled=enabled;self.runner=runner or self._execute;self.lock=threading.RLock();self.thread=None
        self.nonce=secrets.token_urlsafe(32);self.state=None;self.owner_pid=os.getpid()
        # OS lease is released on process death; permanent reservation survives.
        self.handle=(self.root/'gateway.lock').open('a+b')
        try:
            if self.handle.seek(0,os.SEEK_END)==0:self.handle.write(b'0');self.handle.flush()
            self.handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.handle.close();raise LabError(409,'GATEWAY_ALREADY_OWNED')
        self.active=True
        if (self.root/'state.json').exists():
            self.state=c.strict_json((self.root/'state.json').read_bytes())
            c.require(self.state['schema_version']==SCHEMA and self.state['source']=='LIVE'
                and re.fullmatch(r'rpf60-session-[a-f0-9]{16}',self.state['session_id']) is not None,'PERSISTED_SESSION_IDENTITY')
            if self.state['status']=='COMPLETED':
                raw=(self.root/'witness.json').read_bytes();anchor=c.strict_json((self.root/'witness-anchor.json').read_bytes())
                verdict=v.verify_bytes(raw,anchor['sha256']);verdict['verifier_identity']=v.identity()
                checked=projection(c.strict_json(raw)['payload'],'LIVE',anchor['sha256'],len(raw),verdict)
                c.require(all(self.state[k]==checked[k] for k in checked if k!='cancel_requested'),'PERSISTED_DTO_SPLICE')
            if self.state['status'] not in TERMINAL:

                self.state.update(status='RECONCILE_REQUIRED',error_code='RESTART_WITH_UNRESOLVED_EXECUTION');self._save()
    def _save(self):
        raw=c.canonical(self.state);target=self.root/'state.json';tmp=self.root/('state-'+uuid.uuid4().hex+'.tmp')
        with tmp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(tmp,target)
    def _gate(self):
        try:
            gate=c.strict_json((c.WORK/'preflight/ready.json').read_bytes())
            c.require(gate['status']=='PASS' and gate['sources']==c.sources() and gate['verifier']==v.identity(),'SOURCE_OR_FREE_GATE')
            cold=c.strict_json((c.WORK/'preflight/cold-attempt-01/result.json').read_bytes())['capture']
            core.validate_cold_capture(cold)
            c.require(gate['cold_sha256']==c.digest(cold),'COLD_GATE')
            c.require(bool(os.environ.get('DEEPSEEK_API_KEY')),'KEY_MISSING')
            return cold
        except Exception:raise LabError(409,'SOURCE_KEY_SDK_JDK_OR_PREFLIGHT_UNAVAILABLE')
    def capabilities(self):
        reason='SERVER_OPT_IN_REQUIRED'
        if self.enabled:
            try:self._gate();reason='AVAILABLE'
            except LabError as e:reason=e.code
        with self.lock:
            if self.state or (self.root/'session-reserved.json').exists():reason='SESSION_QUOTA_SPENT'
            return {'schema_version':SCHEMA,'enabled':reason=='AVAILABLE','reason':reason,'remaining_sessions':int(reason=='AVAILABLE'),
                'nonce':self.nonce,'limits':c.LIMITS,'requested_model':c.MODEL,'catalog':list(c.CANDIDATES),
                'boundaries':c.BOUNDARIES,'source_sha256':c.digest(c.sources())}
    def create(self,body):
        if type(body) is not dict or set(body)!={'mode','request_id','nonce','confirm_cost_and_simulation'} or body['mode']!='RPF60_CONTROLLED_LIVE' or body['confirm_cost_and_simulation'] is not True or not re.fullmatch(r'[a-f0-9-]{36}',str(body['request_id'])):
            raise LabError(400,'CONFIRMATION_CONTRACT_REQUIRED')
        with self.lock:
            if self.state and self.state['request_id']==body['request_id']:
                if self.state['request_sha256']!=c.digest(body):raise LabError(409,'REQUEST_ID_CONFLICT')
                return self.get(self.state['session_id'])
            if self.state or (self.root/'session-reserved.json').exists():raise LabError(409,'SESSION_QUOTA_SPENT')
            if not self.enabled:raise LabError(409,'SERVER_OPT_IN_REQUIRED')
            if not secrets.compare_digest(body['nonce'],self.nonce):raise LabError(403,'NONCE_REJECTED')
            self._gate()
            sid='rpf60-session-'+uuid.uuid4().hex[:16]
            core.once(self.root/'session-reserved.json',{'session_id':sid,'request_sha256':c.digest(body),'source_sha256':c.digest(c.sources())})
            self.state={'schema_version':SCHEMA,'session_id':sid,'request_id':body['request_id'],'request_sha256':c.digest(body),
                'source':'LIVE','status':'PLANNED','rows':[],'events':[],'witness':None,'usage':{},'reserved_budget':{},
                'boundaries':c.BOUNDARIES,'rationale':'RATIONALE_NOT_RECORDED','research':{},'cancel_requested':False,'error_code':None,
                'source_sha256':c.digest(c.sources())}
            self._save();self.thread=threading.Thread(target=self._work,name='rpf60-owned-session',daemon=False);self.thread.start()
            return self.get(sid)
    def get(self,sid):
        with self.lock:
            if self.state is None or sid!=self.state['session_id']:raise LabError(404,'SESSION_NOT_FOUND')
            result=copy.deepcopy(self.state);result.pop('request_sha256',None)
            return result
    def recover(self,rid):
        with self.lock:
            if self.state is None or rid!=self.state['request_id']:raise LabError(404,'REQUEST_NOT_FOUND')
            return self.get(self.state['session_id'])
    def cancel(self,sid):
        with self.lock:
            self.get(sid)
            if self.state['status'] not in TERMINAL:
                self.state.update(cancel_requested=True,status='CANCEL_REQUESTED');self._save()
            return self.get(sid)
    def checkpoint(self):
        with self.lock:
            if self.state['cancel_requested']:raise LabError(409,'CANCEL_AT_SAFE_BOUNDARY')
    def _work(self):
        try:
            with self.lock:self.state['status']='RUNNING';self._save()
            self.checkpoint();self.runner()
        except Exception as e:
            with self.lock:
                # Spent provider/mutation reservations prevent any subsequent I/O.
                code=getattr(e,'code',type(e).__name__)
                if code=='CANCEL_AT_SAFE_BOUNDARY':status='CANCELLED'
                else:status='RECONCILE_REQUIRED' if (c.WORK/'ledger').exists() else 'PLATFORM_ERROR'
                self.state.update(status=status,error_code=code,witness=None);self._save()
    def _progress(self,ledger,session):
        with self.lock:
            ledger.read()
            self.state['events']=[{'seq':e['seq'],'event_id':'e'+str(e['seq']),'type':e['kind'],'monotonic_ns':e['monotonic_ns'],
                'round':e['data'].get('round'),'domain':e['data'].get('domain')} for e in ledger.state['events']]
            self.state['reserved_budget']=core.validate_state(ledger.state,ledger.plan)
            # Partial rows contain verified feedback only, never a success Witness.
            self.state['rows']=[{'round':r['round'],'candidate_id':r['candidate_id'],'run_id':r['contract']['experiment']['run_id'],
                'target_source':c.BOUNDARIES['target_sources'][r['feedback']['domain']],'authority':r['feedback']['authority'],
                'tool_call_id':r['selection']['id'],'response_id':r['observation']['shape']['response_id'],'feedback':r['feedback'],
                'feedback_sha256':c.digest(r['feedback']),'input':r['input'],'status':'CONTRACT_SATISFIED_IN_RUN'} for r in session.rows]
            self._save()
    def _execute(self):
        cold=self._gate();ports=[]
        while len(ports)<4:
            port=core.old._free_port()
            if port not in ports:ports.append(port)
        slots=[('rpf60-order-'+uuid.uuid4().hex[:16],'rpf60-config-'+uuid.uuid4().hex[:16],*ports[2*i:2*i+2]) for i in range(2)]
        plan=c.plan(self.state['session_id'],slots,c.sources());core.once(c.WORK/'preflight/session-plan.json',plan)
        task=core.TaskGuard(c.WORK/'task-intents')
        n=task.reserve('SESSION',c.digest(c.sources()),plan_sha256=c.digest(plan),cold_capture_sha256=c.digest(cold))
        ledger=core.Ledger(c.WORK/'ledger',plan,create=True);session=core.SharedSession(ledger)
        key=os.environ.get('DEEPSEEK_API_KEY','')
        try:
            for index in (1,2):
                self.checkpoint();body=c.body_for(c.messages_for(session.rows));core.once(c.WORK/'replay'/f'round-{index}-request.json',body)
                data,attempt=c.request(body,ledger,index,key,shape_writer=lambda obs:core.once(c.WORK/'replay'/f'round-{index}-observation.json',obs))
                self._progress(ledger,session);self.checkpoint()
                selection=c.parse_selection(data,{r['selection']['id'] for r in session.rows});del data
                row=session.execute_trial(selection,body,ledger.response_observation,attempt)
                core.once(c.WORK/'replay'/f'round-{index}.json',row);self._progress(ledger,session)
            key=None;ledger.read()
            task.result(n,'PASS',ledger_chain_sha256=c.digest(ledger.chain),rows_sha256=c.digest(session.rows))
            p={'source_kind':v.REAL,'claim':v.CLAIM,'plan':plan,'rows':session.rows,'ledger_chain':ledger.chain,'cold_fixture':cold,
                'task_intents':task.read(),'boundaries':c.BOUNDARIES,'research':v.research(session.rows)}
            raw=c.canonical(v.seal(p))+b'\n';anchor=hashlib.sha256(raw).hexdigest();verdict=v.verify_bytes(raw,anchor);verdict['verifier_identity']=v.identity()
            with (self.root/'witness.json').open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            core.once(self.root/'witness-anchor.json',{'sha256':anchor,'bytes':len(raw)})
            with self.lock:
                extra={k:self.state[k] for k in ('request_id','request_sha256','cancel_requested')}
                self.state=projection(p,'LIVE',anchor,len(raw),verdict)|extra;self._save()
        finally:
            key=None
            self._progress_after_failure(ledger,session)
    def _progress_after_failure(self,ledger,session):
        if self.state['status']!='COMPLETED':self._progress(ledger,session)
    def witness(self,sid):
        s=self.get(sid)
        if s['status']!='COMPLETED' or not s['witness']:raise LabError(409,'WITNESS_NOT_ISSUED')
        raw=(self.root/'witness.json').read_bytes()
        if len(raw)!=s['witness']['bytes']:raise LabError(409,'WITNESS_SIZE_MISMATCH')
        v.verify_bytes(raw,s['witness']['sha256']);return raw
    def close(self):
        if not self.active:return
        if self.thread and self.thread.is_alive():
            self.cancel(self.state['session_id']);self.thread.join(timeout=420)
        if self.thread and self.thread.is_alive():raise LabError(409,'EXECUTION_STILL_UNRESOLVED')
        self.handle.close();self.active=False

def prepare(mode):
    """Free gates only. LIVE can only be started through authenticated Gateway."""
    if mode=='metadata':
        core.old._verify_source_bundle();java=core.old._java_identity();task=core.TaskGuard(c.WORK/'task-intents')
        n=task.reserve('METADATA',c.digest(c.sources()))
        try:sdk=core.sdk_identity_direct()
        except Exception as e:task.result(n,'FAIL',error=type(e).__name__);raise
        if not core.JAR.exists():
            import shutil
            with core.old.SOURCE_JAR.open('rb') as src,core.JAR.open('xb') as dst:shutil.copyfileobj(src,dst)
        c.require(core.JAR.stat().st_size==c.SOURCE_JAR_BYTES and core.old._sha_file(core.JAR)==c.SOURCE_JAR_SHA256,'TASK_JAR')
        identity={'sources':c.sources(),'sdk':sdk,'java':java,'verifier':v.identity()}
        core.once(c.WORK/'preflight'/('identity-'+c.digest(c.sources())+'.json'),identity);task.result(n,'PASS',identity_sha256=c.digest(identity))
    elif mode=='cold':
        path=c.WORK/'preflight'/('identity-'+c.digest(c.sources())+'.json');identity=c.strict_json(path.read_bytes());c.require(identity['sources']==c.sources(),'SOURCE')
        contract=c.trial(c.DOMAINS[1],'rpf60-config-'+uuid.uuid4().hex[:16],c.digest(c.sources()),core.old._free_port(),core.old._free_port())
        result=core.cold_fixture(contract,identity['sdk'])
        core.once(c.WORK/'preflight/ready.json',{'status':'PASS','sources':c.sources(),'verifier':v.identity(),'cold_sha256':c.digest(result['capture'])})
    else:raise ValueError('FREE_MODE_ONLY')
    return {'status':'PASS','mode':mode,'source_sha256':c.digest(c.sources()),'provider':0,'business':0}
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('metadata','cold'));args=p.parse_args()
    print(c.canonical(prepare(args.mode)).decode())
