"""Bounded local calculations: two processes, distinct output folders and logs."""
import concurrent.futures
import subprocess
import sys
from pathlib import Path
from combined_riobamba import SPEC, modes

ROOT = Path(__file__).resolve().parent
LOG = ROOT / 'riobamba-runs/combined-logs'
LOG.mkdir(exist_ok=True)


def execute(job):
    name, mode, dx = job
    log = LOG / f'{name}-{mode}-{dx}.log'
    args = [sys.executable, '-u', str(ROOT / 'combined_riobamba.py'), '--case', name, '--mode', mode, '--dx', str(dx)]
    print('START', name, mode, dx, flush=True)
    with log.open('w', encoding='utf-8') as out:
        result = subprocess.run(args, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT)
    print('DONE' if result.returncode == 0 else 'FAILED', name, mode, dx, 'log', log.name, flush=True)
    return result.returncode


if __name__ == '__main__':
    # Highest-reference runs first, so baseline comparison becomes available early.
    order = ['combined-6h-high', 'prepared-1h-double', 'combined-6h-low',
             'combined-6h-medium', 'prepared-6h-double', 'prepared-12h-repeat']
    jobs = [(name, mode, 24) for name in order for mode in modes(name)]
    jobs += [('combined-6h-high', 'none', 48)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(execute, jobs))
    if any(results):
        raise SystemExit('One or more runs failed; inspect logs before packaging')
    subprocess.run([sys.executable, str(ROOT / 'combined_riobamba.py'), '--pack'], cwd=ROOT, check=True)
