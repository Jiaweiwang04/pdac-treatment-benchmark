"""Build the Pilot review batch without changing the catalog or split."""
import argparse,json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BASE/'code/src'))
from pdac_benchmark.v2_0.pilot_review import build
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',type=Path,default=BASE)
    args=parser.parse_args();sys.stdout.reconfigure(encoding='utf8')
    print(json.dumps(build(BASE,args.output_root),ensure_ascii=False,indent=2))
