"""Apply current evidence wording rules to an existing generated narrative."""

import argparse
from pathlib import Path

from video_demo.narrative import reconcile_narrative


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    report = reconcile_narrative(args.run)
    print(f'Reconciled {len(report["segments"])} segments; overview {len(report["overall"])} characters')
