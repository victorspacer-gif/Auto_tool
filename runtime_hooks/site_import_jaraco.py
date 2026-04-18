# Force-import common jaraco subpackages and pkg_resources early in runtime
try:
    import jaraco.packaging
except Exception:
    pass

try:
    import pkg_resources
except Exception:
    pass
