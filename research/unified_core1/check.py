import json,sys,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[2]
f=json.loads(Path(sys.argv[2]).read_text()).get('format','')
if f=='drnas-math5-eo-xor-unit-v1': p='research/math5/check_math5.py'
elif f=='pcmax-clause-hall-v1':p='research/pcmax_capacity/check_clause_hall.py'
elif f=='pcmax-capacity-v1':p='research/pcmax_capacity/check_capacity.py'
else:raise SystemExit('Unsupported certificate format')
sys.exit(subprocess.call([sys.executable,str(R/p),*sys.argv[1:]]))
