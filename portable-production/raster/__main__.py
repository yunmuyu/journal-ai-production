"""JSON CLI: python -m raster render plan.json."""
import json
import sys
from pathlib import Path

from task_quality.storage import read, ref
from task_quality.models import GateError
from .render import RasterError, render


def main() -> int:
    try:
        if len(sys.argv) != 3 or sys.argv[1] != 'render':
            raise RasterError('usage: python -m raster render plan.json')
        plan = read(Path(sys.argv[2]))
        result = render(plan)
        report = Path(result['output']['path']).with_suffix('.raster.json')
        print(json.dumps(dict(ok=True, status='candidate', report=ref(report), result=result), ensure_ascii=False))
        return 0
    except (RasterError, GateError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps(dict(ok=False, error=str(exc)), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
