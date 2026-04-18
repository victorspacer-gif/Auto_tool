# purecase

Modulo Python para localizar uma instalacao do PureCase ou Sandboxie-Plus, criar/configurar boxes e iniciar processos com `Start.exe`.

## Exemplo rapido

```python
from pathlib import Path

from purecase import find_installation, launch_in_box

project_root = Path(__file__).resolve().parent
installation = find_installation(project_root=project_root)
if installation is None:
    raise RuntimeError("PureCase/Sandboxie nao encontrado.")

launch_in_box(
    installation,
    box_name="TargetBox01",
    executable=r"C:\caminho\app.exe",
    args=["--mode", "safe"],
)
```

## API principal

- `find_installation(...)`
- `ensure_box(...)`
- `configure_box(...)`
- `launch_in_box(...)`
- `list_box_pids(...)`
- `terminate_box(...)`
