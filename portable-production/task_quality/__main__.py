"""JSON CLI: python -m task_quality PHASE CONTRACT [SUBMISSION_OR_REVIEW]."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .gate import finalize, postcheck, precheck, verify
from .models import GateError
from .storage import read


def main() -> int:
    try:
        args = sys.argv[1:]
        if len(args) not in (2, 3):
            raise GateError('usage', 'PHASE CONTRACT [SUBMISSION_OR_REVIEW]')
        phase, filename = args[:2]
        contract = read(Path(filename))
        match phase:
            case 'precheck' | 'verify':
                if len(args) != 2:
                    raise GateError('usage', 'Phase takes CONTRACT only')
                result = precheck(contract) if phase == 'precheck' else verify(contract)
            case 'postcheck' | 'finalize':
                if len(args) != 3:
                    raise GateError('usage', 'Phase requires a submission/review JSON file')
                evidence = read(Path(args[2]))
                result = postcheck(contract, evidence) if phase == 'postcheck' else finalize(contract, evidence)
            case _:
                raise GateError('usage', f'Unknown phase: {phase}')
        print(json.dumps(dict(ok=True, phase=phase, result=result), ensure_ascii=False, allow_nan=False))
        return 0
    except GateError as exc:
        print(json.dumps(dict(ok=False, error=dict(code=exc.code, detail=exc.detail)), ensure_ascii=False))
        return 1
    except OSError as exc:
        print(json.dumps(dict(ok=False, error=dict(code='io_error', detail=str(exc))), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
