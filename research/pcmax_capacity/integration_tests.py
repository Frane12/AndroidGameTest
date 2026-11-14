"""Portable integration checks for the opt-in native PCMAX module."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import tempfile
import time

WITNESS_CNF = 'p cnf 20 32\n1 2 0\n-1 -2 0\n3 4 0\n-3 -4 0\n5 6 0\n-5 -6 0\n5 -9 7 0\n-5 -9 7 0\n5 -10 7 0\n-5 -10 8 0\n3 -11 9 0\n-3 -11 10 0\n3 -12 10 0\n-3 -12 8 0\n1 -13 11 0\n-1 -13 12 0\n13 0\n7 0\n-8 0\n6 -16 14 0\n-6 -16 14 0\n6 -17 14 0\n-6 -17 15 0\n4 -18 16 0\n-4 -18 17 0\n4 -19 17 0\n-4 -19 15 0\n2 -20 18 0\n-2 -20 19 0\n20 0\n14 0\n-15 0\n'

REPO = Path(__file__).resolve().parents[2]
NATIVE = BASE = WORK = CHECK = checker = None
CPU = None
rows=[]


def fixtures():
    # Genuine identical-machine scheduling: jobs [6,6,6], two machines, T=10.
    # Job literals are disjoint exactly-one groups; each machine has its own BDD.
    source = WITNESS_CNF.encode('ascii')
    (WORK/'witness.cnf').write_bytes(source)
    (WORK/'witness-crlf-no-final.cnf').write_bytes(b'c exact bytes\r\n'+source.rstrip(b'\n').replace(b'\n',b'\r\n'))
    (WORK/'witness-percent.cnf').write_bytes(b'% extra dialect\n'+source)
    (WORK/'witness-prefixed-comment.cnf').write_bytes(b'comment extra dialect\n'+source)
    (WORK/'witness-inline-comment.cnf').write_bytes(source.replace(b'1 2 0\n',b'1 2 0 c inline\n',1))
    (WORK/'witness-nonascii-comment.cnf').write_bytes(b'c nonascii \xc3\xa9\n'+source)
    (WORK/'sat.cnf').write_bytes(b'p cnf 2 3\n1 2 0\n-1 2 0\n1 -2 0\n')
    (WORK/'header-overlimit.cnf').write_bytes(b'p cnf 200001 0\n')
    (WORK/'header-huge.cnf').write_bytes(b'p cnf 10000000 0\n')
    (WORK/'header-huge-dialect.cnf').write_bytes(b'% unsupported comment\np cnf 10000000 0\n')
    (WORK/'literal-overlimit.cnf').write_bytes(b'p cnf 1 1\n'+b'1 '*10000001+b'0\n')
    (WORK/'deadline.cnf').write_bytes(b'c deadline\n'*10000+b'p cnf 0 0\n')


def run(name, input='witness.cnf', flags=(), binary=None, limit_write=False, memory_limit=None):
    if binary is None: binary=NATIVE
    command=[str(binary),str(WORK/input),'--mode','core','--time','2',*map(str,flags)]
    def before():
        if CPU is not None: os.sched_setaffinity(0,{CPU})
        if memory_limit is not None: resource.setrlimit(resource.RLIMIT_AS,(memory_limit,memory_limit))
        if limit_write:
            resource.setrlimit(resource.RLIMIT_FSIZE,(512,512))
            signal.signal(signal.SIGXFSZ,signal.SIG_IGN)
    started=time.perf_counter()
    result=subprocess.run(command,text=True,capture_output=True,timeout=5,preexec_fn=before)
    row=dict(name=name,command=command,returncode=result.returncode,stdout=result.stdout,
             stderr=result.stderr,wall_s=time.perf_counter()-started,memory_limit_bytes=memory_limit)
    telemetry=[line[len('c PCMAX_CAPACITY '):] for line in result.stdout.splitlines() if line.startswith('c PCMAX_CAPACITY ')]
    row['telemetry']=json.loads(telemetry[0]) if telemetry else None
    rows.append(row)
    return row

def cert(name):
    path=WORK/(name+'.json')
    if path.is_symlink() or path.exists(): path.unlink()
    return path

def assert_error(row):
    assert row['returncode']==1,row
    assert 's UNSATISFIABLE' not in row['stdout'],row


def checks():
    started=time.perf_counter()
    # Successful certificates are independently checked against exact raw bytes.
    for fixture in ('witness.cnf','witness-crlf-no-final.cnf'):
        output=cert(fixture)
        row=run('verified-'+fixture,input=fixture,flags=['--pcmax-only','--pcmax-certificate',output])
        assert row['returncode']==20,row
        assert row['telemetry']['verified'] is True,row
        data=json.loads(output.read_text())
        actual_hash=hashlib.sha256((WORK/fixture).read_bytes()).hexdigest()
        assert data['source_sha256']==actual_hash,(row,data)
        checked=checker.check((WORK/fixture).read_bytes(),data)
        assert checked['status']=='UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED',checked
        row['independent_check']=checked

    # No path means no structural UNSAT; the discovery-only mode stays UNKNOWN.
    row=run('missing-certificate',flags=['--pcmax-only'])
    assert row['returncode']==0 and row['telemetry']['reason']=='certificate_path_required',row

    # Negative/unsupported input falls through to the same original CDCL result.
    base=run('base-sat',input='sat.cnf',flags=['--stats'],binary=BASE)
    disabled=run('native-disabled-sat',input='sat.cnf',flags=['--stats'])
    fallback=run('native-fallback-sat',input='sat.cnf',flags=['--pcmax-capacity','--stats'])
    assert base['returncode']==disabled['returncode']==fallback['returncode']==10
    assert disabled['telemetry'] is None
    def core_stats(row):
        found=[json.loads(line[len('X41_STATS '):]) for line in row['stderr'].splitlines() if line.startswith('X41_STATS ')]
        assert len(found)==1,row
        return {key:found[0][key] for key in ('status','decisions','conflicts','propagations','learnt','restarts')}
    assert core_stats(base)==core_stats(disabled)==core_stats(fallback)

    # DRAT requests disable the module; no structural certificate is emitted.
    proof=WORK/'witness.drat'
    proof.unlink(missing_ok=True)
    output=cert('proof-unused')
    row=run('proof-disables-module',flags=['--pcmax-capacity','--proof',proof,'--pcmax-certificate',output])
    assert row['returncode']==20 and row['telemetry']['reason']=='disabled_for_drat',row
    assert not output.exists() and proof.read_bytes().endswith(b'0\n'),row
    forbidden_proof=WORK/'forbidden-proof.drat'
    forbidden_proof.unlink(missing_ok=True)
    row=run('proof-only-rejected',flags=['--pcmax-only','--proof',forbidden_proof])
    assert_error(row)
    assert not forbidden_proof.exists()

    for fixture in ('witness-percent.cnf','witness-prefixed-comment.cnf',
                    'witness-inline-comment.cnf','witness-nonascii-comment.cnf'):
        row=run('dialect-gate-'+fixture,input=fixture,flags=['--pcmax-only'])
        assert row['returncode']==0 and row['telemetry']['reason']=='unsupported_dimacs_dialect',row
    row=run('oversize-budget-rejected',flags=['--pcmax-only','--pcmax-budget-ms','1e300','--time','0'])
    assert_error(row)

    # Existing destinations, input aliases, and symlinks cannot be overwritten.
    sentinel=cert('existing')
    sentinel.write_text('keep-this-file\n')
    row=run('existing-rejected',flags=['--pcmax-only','--pcmax-certificate',sentinel])
    assert_error(row)
    assert sentinel.read_text()=='keep-this-file\n'
    input_path=WORK/'witness.cnf'
    original=input_path.read_bytes()
    aliases=[input_path,WORK/'input-hardlink.json',WORK/'input-symlink.json']
    for path in aliases[1:]:
        path.unlink(missing_ok=True)
    os.link(input_path,aliases[1])
    aliases[2].symlink_to(input_path)
    for path in aliases:
        row=run('alias-rejected-'+path.name,flags=['--pcmax-only','--pcmax-certificate',path])
        assert_error(row)
        assert input_path.read_bytes()==original
    parent_link=WORK/'parent-symlink'
    if parent_link.is_symlink(): parent_link.unlink()
    parent_link.symlink_to(WORK,target_is_directory=True)
    output=cert('parent-symlink-output')
    row=run('parent-symlink-rejected',flags=['--pcmax-only','--pcmax-certificate',parent_link/output.name])
    assert_error(row)
    assert not output.exists()
    missing=WORK/'missing-directory'/'out.json'
    row=run('write-open-error',flags=['--pcmax-only','--pcmax-certificate',missing])
    assert_error(row)
    output=cert('write-size-error')
    row=run('write-size-error',flags=['--pcmax-only','--pcmax-certificate',output],limit_write=True)
    assert_error(row)
    assert not output.exists()
    assert not list(WORK.glob('.pcmax-certificate-*.tmp'))

    # Explicit skip and total-deadline paths cannot invoke unbounded discovery.
    row=run('zero-module-budget',flags=['--pcmax-only','--pcmax-budget-ms','0'])
    assert row['returncode']==0 and row['telemetry']['budget_s']==0,row
    row=run('total-deadline-includes-read',input='deadline.cnf',flags=['--pcmax-only','--time','0.000001'])
    assert row['returncode']==0 and row['telemetry']['reason']=='overall_time_exhausted_during_read',row
    row=run('budget-clamped',flags=['--pcmax-only','--pcmax-budget-ms','10000','--time','1'])
    assert row['returncode']==0 and 0<row['telemetry']['budget_s']<=1,row
    row=run('declared-variable-limit',input='header-overlimit.cnf',flags=['--pcmax-only'])
    assert row['returncode']==0 and row['telemetry']['reason']=='header_size_gate',row
    for fixture in ('header-huge.cnf','header-huge-dialect.cnf'):
        row=run('huge-header-without-cdcl-allocation-'+fixture,input=fixture,flags=['--pcmax-only'],memory_limit=128*1024*1024)
        assert row['returncode']==0 and row['telemetry']['reason']=='header_size_gate',row
        assert row['telemetry']['source_sha256']=='',row
    row=run('baseline-huge-header-exceeds-address-limit',input='header-huge.cnf',binary=BASE,memory_limit=128*1024*1024)
    assert_error(row)
    row=run('discovery-literal-limit',input='literal-overlimit.cnf',flags=['--pcmax-only'])
    assert row['returncode']==0 and row['telemetry']['reason']=='literal_size_gate',row
    assert row['telemetry']['source_sha256']=='',row
    result=dict(checks=len(rows),passed=True,wall_s=time.perf_counter()-started,
                source_hashes={str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (REPO/'src/drnas_x5.cpp',REPO/'src/pcmax_capacity.hpp',CHECK)},
                binary_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (NATIVE,BASE)},rows=rows)
    return result


def main():
    global NATIVE, BASE, WORK, CHECK, checker, CPU
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,default=REPO/'build/drnas-pcmax')
    parser.add_argument('--base-binary',type=Path,default=REPO/'build/drnas-pcmax-base')
    parser.add_argument('--checker',type=Path,default=Path(__file__).with_name('check_capacity.py'))
    parser.add_argument('--work-dir',type=Path)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--cpu',type=int,help='Pin child processes to this available CPU; default first available CPU')
    args=parser.parse_args()
    NATIVE,BASE,CHECK=(p.resolve() for p in (args.binary,args.base_binary,args.checker))
    if hasattr(os,'sched_getaffinity'):
        available=os.sched_getaffinity(0)
        CPU=min(available) if args.cpu is None else args.cpu
        if CPU not in available: parser.error('Requested CPU is outside process affinity')
    elif args.cpu is not None:
        parser.error('CPU pinning is unavailable on this platform')
    spec=importlib.util.spec_from_file_location('independent_capacity_check',CHECK)
    checker=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    with tempfile.TemporaryDirectory(prefix='drnas-pcmax-integration-') as temporary:
        WORK=args.work_dir.resolve() if args.work_dir else Path(temporary)
        WORK.mkdir(parents=True,exist_ok=True)
        fixtures()
        result=checks()
        if args.report:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))


if __name__=='__main__':
    main()
