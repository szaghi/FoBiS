## Instructions for building and uploading FoBiS.py to PyPi

### Prepare before build

In `release` branch, bump verion number in `src/main/python/fobis/FoBiSConfig.py`, e.g. `__version__ = "3.0.6"`.
Commit the file changed.

### Build

In repo root type

```bash
pyb
```

This creates a `release/FoBiS-release-v3.0.6/` directory, build the package and test it.

If `pyb` is not installed, install it via pip

```bash
pip install pybuilder
```

### Upload the package to PyPi

Enter release directory, prepare the package distribution and upload it:

```bash
cd release/FoBiS-release-v3.0.6/
python setup.py sdist
twine upload dist/*
```

After a successful upload, a message like the following is printed:

```bash
Uploading distributions to https://upload.pypi.org/legacy/
Uploading FoBiS.py-3.0.6.tar.gz
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 54.4/54.4 kB • 00:00 • 142.4 MB/s

View at:
https://pypi.org/project/FoBiS.py/3.0.6/
```

If `twine` is not installed, install it via pip

```bash
pip install twine
```
