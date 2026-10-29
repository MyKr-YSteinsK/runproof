"""Finite owned TCP sink and host roles; no external addresses or SDK."""
import os
import socket
import struct
import threading
import time
from . import pge_r81_contracts as c
from .pge_r81_barrier import Host


def wait_file(path,timeout=8,process=None):
    p=c.scope(path);deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if p.is_file():return p
        if process is not None and process.poll() is not None:raise ValueError('CHILD_EXIT_BEFORE_READY')
        time.sleep(.01)
    raise ValueError('CONTROL_HANDSHAKE_TIMEOUT')


def receiver(case_id):
    spec=c.spec(case_id);c.require(spec['localhost'],'RECEIVER_SCOPE')
    root=c.scope(c.WORK/'receivers'/case_id);root.mkdir(parents=True,exist_ok=False)
    raw=b'';chunks=[];connections=0;received_mono=None;status='NO_CONNECTION';start=c.clock()
    server=socket.socket(socket.AF_INET,socket.SOCK_STREAM);server.settimeout(.1)
    try:
        server.bind(('127.0.0.1',0));server.listen(1);address,port=server.getsockname();c.require(address=='127.0.0.1','BIND_SCOPE')
        if spec['scenario']=='connect-fail':server.close();status='LISTENER_CLOSED'
        c.once(root/'ready.json',dict(address=address,port=port,case_id=case_id,source=c.source_id(),**c.clock()))
        deadline=time.monotonic()+12
        while spec['scenario']!='connect-fail' and time.monotonic()<deadline and not (root/'stop.json').exists():
            try:conn,peer=server.accept()
            except socket.timeout:continue
            c.require(peer[0]=='127.0.0.1' and connections<4,'PEER_SCOPE');connections+=1;conn.settimeout(4)
            if spec['scenario']=='reset':
                conn.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('hh' if os.name=='nt' else 'ii',1,0));conn.close()
                c.once(root/'reset.json',dict(status='RESET_CLOSED',**c.clock()));status='RESET_CLOSED';break
            try:
                if spec['scenario']=='race-send':wait_file(root/'release.json')
                while True:
                    chunk=conn.recv(4097)
                    if not chunk:break
                    c.require(len(raw)+len(chunk)<=4096,'RECEIVER_BOUND');raw+=chunk;received_mono=time.monotonic();chunks.append(dict(size=len(chunk),sha256=c.sha(chunk),mono=received_mono))
                status='RECEIVED' if raw else 'NO_BYTES'
            finally:conn.close()
        c.require((root/'stop.json').exists() or spec['scenario'] in ('connect-fail','reset'),'RECEIVER_STOP_TIMEOUT')
    finally:server.close()
    with (root/'received.raw').open('xb') as file:file.write(raw);file.flush();os.fsync(file.fileno())
    c.once(root/'receipt.json',dict(case_id=case_id,source=c.source_id(),owner=c.OWNER,address='127.0.0.1',port=port,status=status,connections=connections,bytes=len(raw),raw_sha256=c.sha(raw),chunks=chunks,received_mono=received_mono,start=start,**c.clock()))
    return dict(status='RECEIVER_CLOSED',case_id=case_id,bytes=len(raw),pid=os.getpid())


def host(case_id,phase,port):
    spec=c.spec(case_id);scenario=spec['scenario'];h=Host(case_id,create=phase!='recover');start=c.clock()
    try:
        if phase=='prepare':
            h.reserve();h.unknown();print(c.canonical(dict(status='CRASH_AFTER_DURABLE_UNKNOWN',**c.clock())).decode(),flush=True);os._exit(23)
        if phase=='recover':
            for domain in ('config','order'):
                for role in ('TARGET','EXPLORER'):c.require(h.reserve(domain,role)=='DENY','RECOVERY_RESERVE')
            c.require(h.send('ticket-1',port)=='DENY','RECOVERY_OLD_SEND');h.reconcile();h.terminal()
        elif scenario=='normal':ticket=h.reserve();c.require(h.send(ticket,port)=='ALLOW','NORMAL_SEND');h.terminal()
        elif scenario in ('old','new','readonly','race-unknown','race-send'):
            ticket=h.reserve()
            if scenario in ('race-send','race-unknown'):
                first=threading.Event();second=threading.Event();errors=[]
                def sender():
                    try:
                        if scenario=='race-unknown':c.require(first.wait(4),'UNKNOWN_WAIT');c.require(h.send(ticket,port)=='DENY','UNKNOWN_WINS')
                        else:c.require(h.send(ticket,port,sent_event=first,release_event=second)=='ALLOW','SEND_WINS')
                    except BaseException as exc:errors.append(repr(exc))
                def observer():
                    try:
                        if scenario=='race-send':c.require(first.wait(4),'SEND_WAIT');h.unknown(contended=second);c.once(c.WORK/'receivers'/case_id/'release.json',dict(**c.clock()))
                        else:h.unknown();first.set()
                    except BaseException as exc:errors.append(repr(exc));second.set();first.set()
                threads=[threading.Thread(target=f,daemon=True) for f in (sender,observer)]
                for thread in threads:thread.start()
                for thread in threads:thread.join(6)
                c.require(not errors and not any(t.is_alive() for t in threads),'RACE_INCONCLUSIVE:'+repr(errors))
            else:
                h.unknown()
                if scenario=='old':c.require(h.send(ticket,port)=='DENY','OLD_SEND')
                if scenario=='new':
                    for domain in ('config','order'):
                        for role in ('TARGET','EXPLORER'):c.require(h.reserve(domain,role)=='DENY','NEW_RESERVE')
            h.reconcile();h.terminal()
        elif scenario in ('persist-write','persist-fsync'):
            ticket=h.reserve();c.require(h.unknown(inject=scenario.split('-')[1])=='INCONCLUSIVE','PERSIST_INJECTION')
            c.require(h.send(ticket,port)=='DENY' and h.reserve()=='DENY','PERSIST_FAIL_STOP');h.reconcile();h.terminal()
        elif scenario in ('connect-fail','reset'):
            ticket=h.reserve();h.send(ticket,port,reset_marker=c.WORK/'receivers'/case_id/'reset.json' if scenario=='reset' else None)
            if not (h.root/'unknown-intent.json').exists():h.unknown()
            h.reconcile();h.terminal()
        else:raise ValueError('HOST_SCENARIO')
        summary=dict(status='HOST_CLOSED',case_id=case_id,phase=phase,source=c.source_id(),start=start,**c.clock())
        c.once(c.WORK/'runs'/case_id/('host-'+phase+'.json'),summary);return summary
    finally:h.close()
