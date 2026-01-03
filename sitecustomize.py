import sys
import types


def _ensure_torchvision_functional_tensor() -> None:
    try:
        import torchvision.transforms.functional as functional
    except Exception:
        return

    module_name = "torchvision.transforms.functional_tensor"
    if module_name in sys.modules:
        return

    shim = types.ModuleType(module_name)
    if hasattr(functional, "rgb_to_grayscale"):
        shim.rgb_to_grayscale = functional.rgb_to_grayscale
    sys.modules[module_name] = shim


_ensure_torchvision_functional_tensor()


def _restore_numpy_aliases() -> None:
    try:
        import numpy as np
    except Exception:
        return
    if not hasattr(np, "float"):
        np.float = float  # type: ignore[attr-defined]
    if not hasattr(np, "int"):
        np.int = int  # type: ignore[attr-defined]
    if not hasattr(np, "bool"):
        np.bool = bool  # type: ignore[attr-defined]


_restore_numpy_aliases()
