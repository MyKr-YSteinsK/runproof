"""Host gate: replay->SEND_BEGIN->sendall stays inside one serial lock."""
import socket
import threading
from . import pge_r81_contracts as c
from .pge_r81_journal import Journal


class Host:
    def __init__(self,case_id,create=False):
        self.journal=Journal(case_id,create);self.case_id=case_id;self.root=self.journal.root;self.recovered=not create;self.pending_unknown=False
    def close(self):self.journal.close()
    def op(self,action,decision,**fields):
        c.append(self.root/'operations.jsonl',dict(action=action,decision=decision,**fields,**c.clock()));return decision
    def blocked(self):
        try:state=self.journal.read()
        except (OSError,ValueError):
            if self.journal.poison or self.pending_unknown:return dict(terminal=False,tickets={}),True
            raise
        return state,self.journal.poison or self.pending_unknown or state['unknown'] or (self.root/'unknown-intent.json').exists() or self.recovered
    def reserve(self,domain='config',role='TARGET'):
        with c.serial(self.journal.mutex):
            state,blocked=self.blocked()
            if blocked or state['terminal']:return self.op('reserve','DENY',domain=domain,role=role)
            ticket='ticket-'+str(len(state['tickets'])+1);self.journal.append('SLOT_RESERVED',ticket=ticket,domain=domain,role=role)
            self.op('reserve','ALLOW',ticket=ticket,domain=domain,role=role);return ticket
    def unknown(self,inject=None,contended=None):
        self.pending_unknown=True
        try:return self._commit_unknown(inject,contended)
        except (OSError,ValueError) as exc:
            self.journal.poison=True
            if not (self.root/'persist-failure.json').exists():c.once(self.root/'persist-failure.json',dict(status='PERSIST_FAILURE_INCONCLUSIVE',injection=inject,reason=type(exc).__name__,**c.clock()))
            return self.op('unknown','INCONCLUSIVE',reason='UNKNOWN_COMMIT_UNAVAILABLE')
    def _commit_unknown(self,inject,contended):
        if contended is not None:
            acquired=self.journal.mutex.acquire(blocking=False)
            if acquired:self.journal.mutex.release()
            self.op('unknown_lock','ACQUIRED' if acquired else 'CONTENDED');contended.set()
        with c.serial(self.journal.mutex):
            observation=c.clock();c.once(self.root/'unknown-intent.json',dict(case_id=self.case_id,source=self.journal.source,planned=True,triggered=True,observed=True,agent_exposed=False,**observation))
            try:
                frame=self.journal.append('UNKNOWN_OBSERVED',inject=inject,domain='config',role='TARGET',observed_mono=observation['mono'],planned=True,triggered=True,observed=True,agent_exposed=False)
                c.once(self.root/'unknown-commit.json',dict(seq=frame['seq'],frame_sha256=frame['sha256'],case_id=self.case_id,source=self.journal.source,**c.clock()))
                return self.op('unknown','COMMITTED',seq=frame['seq'])
            except OSError:
                self.journal.poison=True;c.once(self.root/'persist-failure.json',dict(status='PERSIST_FAILURE_INCONCLUSIVE',injection=inject,**c.clock()))
                return self.op('unknown','INCONCLUSIVE',reason='PERSIST_FAILURE')
    def send(self,ticket,port,reset_marker=None,sent_event=None,release_event=None):
        with c.serial(self.journal.mutex):
            state,blocked=self.blocked()
            if blocked or state['terminal'] or ticket not in state['tickets'] or state['tickets'][ticket]['sent']:
                return self.op('send','DENY',ticket=ticket)
            payload=c.spec(self.case_id)['payload'].encode();c.require(type(port) is int and 1024<=port<=65535,'LOOPBACK_PORT')
            ready=c.strict(c.scope(c.WORK/'receivers'/self.case_id/'ready.json').read_bytes())
            c.require(ready['address']=='127.0.0.1' and ready['port']==port and ready['case_id']==self.case_id and ready['source']==self.journal.source,'OWNED_RECEIVER_BINDING')
            sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM);sock.settimeout(3)
            try:
                c.append(self.root/'calls.jsonl',dict(phase='CONNECT_ENTER',ticket=ticket,**c.clock()))
                sock.connect(('127.0.0.1',port))
                if reset_marker:
                    from .pge_r81_loopback import wait_file
                    wait_file(reset_marker)
                self.journal.append('SEND_BEGIN',ticket=ticket,payload_sha256=c.sha(payload),size=len(payload))
                c.claim_send(self.case_id,ticket,payload)
                c.append(self.root/'calls.jsonl',dict(phase='SENDALL_ENTER',ticket=ticket,payload_sha256=c.sha(payload),size=len(payload),source=self.journal.source,**c.clock()))
                sock.sendall(payload)
                c.append(self.root/'calls.jsonl',dict(phase='SENDALL_RETURN',ticket=ticket,status='RETURNED',**c.clock()))
                if sent_event is not None:
                    c.require(c.spec(self.case_id)['scenario']=='race-send','HOOK_SCOPE');sent_event.set();c.require(release_event.wait(4),'RACE_SYNC_TIMEOUT')
                self.journal.append('SEND_END',ticket=ticket,outcome='RETURNED')
                return self.op('send','ALLOW',ticket=ticket)
            except OSError as exc:
                c.append(self.root/'calls.jsonl',dict(phase='IO_EXCEPTION',ticket=ticket,error=type(exc).__name__,**c.clock()))
                self.unknown();return self.op('send','INCONCLUSIVE',ticket=ticket,reason='IO_EXCEPTION')
            finally:sock.close()
    def reconcile(self):
        with c.serial(self.journal.mutex):
            try:
                state=self.journal.read()
                if self.journal.poison:return self.op('reconcile','INCONCLUSIVE',reason='PERSIST_FAILURE')
                self.journal.append('READ_ONLY_RECONCILE',status='LOCAL_JOURNAL_READ_ONLY')
                return self.op('reconcile','ALLOW',unknown=state['unknown'])
            except (OSError,ValueError):return self.op('reconcile','INCONCLUSIVE',reason='JOURNAL_INVALID')
    def terminal(self):
        with c.serial(self.journal.mutex):
            if self.journal.poison:return self.op('terminal','INCONCLUSIVE',reason='PERSIST_FAILURE')
            self.journal.append('SESSION_TERMINAL',status='TERMINATED');return self.op('terminal','ALLOW')
