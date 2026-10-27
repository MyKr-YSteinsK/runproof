"""Versioned factory owning both domains' real fixed-SDK launches."""
from contextvars import ContextVar
from pathlib import Path
import os
import subprocess
import sys
import time
from . import pge_r74_contracts as c
from .pge_r74_launch_contract import LaunchRequest
from .pge_r74_domain_ports import ConfigPort, OrderPort
from .pge_r74_sdk_harness import Harness

ACTIVE = ContextVar('rpf74_factory_launch', default=None)

def _observe_popen(event, args):
    active = ACTIVE.get()
    if event != 'subprocess.Popen' or active is None:
        return
    value, observations = active
    c.require(type(args) is tuple and len(args) == 4 and args[0] is None and
              args[1] == value['windows_command'] and args[2] == value['cwd'] and
              dict(args[3]) == value['env'], 'ACTUAL_POPEN_ARGUMENTS_ENV')
    observations.append(dict(command_sha256=c.sha(args[1].encode()), cwd_sha256=c.sha(args[2].encode()),
                             env_sha256=c.digest(dict(args[3])), env_keys=sorted(args[3])))
    c.require(len(observations) == 1, 'ONE_POPEN_OBSERVATION')

sys.addaudithook(_observe_popen)

class LaunchFactory:
    def launch(self, ctx, ct, ledger, port, request):
        c.require(type(request) is LaunchRequest and type(port) in (ConfigPort, OrderPort) and
                  port.domain == ct['experiment']['domain'] and ledger.ctx is ctx, 'FACTORY_TYPED_BINDING')
        value = request.check(ctx, ct)
        domain, index = port.domain, ct['experiment']['round']
        folder = ctx.scope(Path(value['cwd']))
        folder.mkdir(parents=True, exist_ok=False)
        ctx.once(folder/'launch-input.json', value)
        with ledger.authorized('driver', domain=domain, tool='driver'):
            sdk_ticket = ledger.reserve('sdk', domain=domain, round=index)
            host_ticket = ledger.reserve('host', domain=domain, round=index)
        host = Harness(ctx, ct, ledger, port, value)
        proc = None; observations = []; start_ns = time.time_ns(); started = time.monotonic()
        stdout = stderr = b''; report = None; error = None; cleanup = {}
        try:
            host.start()
            token = ACTIVE.set((value, observations))
            try:
                proc = subprocess.Popen(value['argv'], cwd=value['cwd'], env=value['env'], shell=False,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
            finally:
                ACTIVE.reset(token)
            host.pid = proc.pid
            c.require(len(observations) == 1 and observations[0]['env_sha256'] == value['env_summary']['sha256'],
                      'ACTUAL_ENV_OBSERVATION')
            ledger.append('PROCESS_START', domain=domain, round=index, resource='sdk', pid=proc.pid,
                parent_pid=os.getpid(), started_unix_ns=start_ns, cfg_sha256=value['cfg_sha256'],
                executable_sha256=__import__('runtime.runproof_runtime.effectwitness.pge_r73_contracts',
                    fromlist=['PIN']).PIN['python_executable_sha256'])
            stdout, stderr = proc.communicate(c.canonical(value['cfg']), timeout=value['timeout_seconds'])
            for name, raw in (('stdout.raw', stdout), ('stderr.raw', stderr)):
                with ctx.scope(folder/name).open('xb') as stream:
                    stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            report = c.strict(stdout)
            c.require(proc.returncode == 0 and not stderr and host.failure is None and
                      report.get('status') == 'COMPLETED' and report.get('pid') == proc.pid and host.ready is not None,
                      'SDK_COMPLETION')
            c.require(report.get('requests') == len(host.rows) and report.get('tool_calls') == len(host.callbacks) and
                      report.get('tool_callbacks') == len(host.callbacks) and
                      report.get('input_tokens') == sum(r['response']['usage']['prompt_tokens'] for r in host.rows) and
                      report.get('output_tokens') == sum(r['response']['usage']['completion_tokens'] for r in host.rows) and
                      not report.get('provider_key_present') and not report.get('business_key_present') and
                      not report.get('guard_denials') and not report.get('denied_files') and
                      report.get('final_text_persisted') is False, 'SDK_REPORT')
            f = host.fault.public()
            c.require((not any(f[k] for k in ('planned','triggered','observed','agent_exposed'))) if ctx.scenario == 'N'
                      else all(f[k] for k in ('planned','triggered','observed','agent_exposed')), 'FAULT_FOUR_STATES')
        except BaseException as exc:
            error = {'type':type(exc).__name__, 'code':str(exc) if type(exc) is ValueError else 'PROCESS_OR_HOST_ERROR'}
        finally:
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=15)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=10)
            cleanup = host.close()
            cleanup['process_gone'] = proc is None or proc.poll() is not None
            with ledger.authorized('driver', domain=domain, tool='driver'):
                ledger.settle(host_ticket, status='CLOSED')
                ledger.settle(sdk_ticket, status='COMPLETED' if error is None else 'UNKNOWN')
            ledger.append('PROCESS_CLEANUP', domain=domain, round=index, resource='sdk',
                          pid=proc.pid if proc else None, **cleanup)
        receipt = dict(factory='pge_r74_launch_factory.LaunchFactory.launch', owner=c.OWNER, abi=c.ABI,
            source_kind=c.SOURCE_KIND, source_sha256=ctx.source.raw_sha256, request_sha256=request.raw_sha256,
            cfg_sha256=value['cfg_sha256'], env_observation=observations, pid=proc.pid if proc else None,
            parent_pid=os.getpid(), started_unix_ns=start_ns, elapsed_seconds=time.monotonic()-started,
            exit=proc.returncode if proc else None, stdout_sha256=c.sha(stdout), stderr_sha256=c.sha(stderr),
            report=report, ready=host.ready, rows=host.rows, callbacks=host.callbacks, fault=host.fault.public(),
            error=error, cleanup=cleanup, model_source='SCRIPTED_PROVIDER', issuer=False)
        ctx.once(folder/'launch-receipt.json', receipt)
        c.require(error is None and all(cleanup.values()), 'FACTORY_UNKNOWN_OR_CLEANUP')
        return receipt
