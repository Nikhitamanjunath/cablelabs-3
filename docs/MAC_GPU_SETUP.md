# Using Apple Silicon GPU for ML Notebooks

The ML notebooks (e.g. 10, 11–26) use TensorFlow. On Apple Silicon, TensorFlow can use the GPU via the **tensorflow-metal** plugin, which often gives a noticeable speedup for training.

## Option A: Python 3.11 environment (recommended)

**tensorflow-metal** has no official wheel for Python 3.13. The reliable way to get GPU is to use **Python 3.11** for the ML environment.

1. **Install Python 3.11** (if needed):
   - Homebrew: `brew install python@3.11`
   - pyenv: `pyenv install 3.11.9` then `pyenv local 3.11.9`
   - Or download from [python.org](https://www.python.org/downloads/).

2. **Create a GPU-enabled venv** (from repo root):
   ```bash
   python3.11 -m venv .venv-gpu
   source .venv-gpu/bin/activate   # or: .venv-gpu\Scripts\activate on Windows
   pip install --upgrade pip
   pip install -r requirements-mac-gpu.txt
   ```

3. **Run Jupyter with this kernel**:
   ```bash
   python -m ipykernel install --user --name=cablelabs-gpu
   ```
   Then in Jupyter: **Kernel → Change kernel → cablelabs-gpu**.

4. Re-run the notebooks; the GPU cell should report something like `GPU enabled: 1 device(s)` and use the larger batch size (e.g. 128).

## Option B: Stay on Python 3.13 (CPU only for now)

- Keep using your current venv and `requirements.txt`. The notebooks run fine on CPU (smaller batch size).
- When **tensorflow-metal** adds Python 3.13 support, install it with:
  ```bash
  pip install tensorflow-metal
  ```
  Then restart the Jupyter kernel and re-run.

## Option C: Manual Metal plugin on 3.13 (unsupported)

Some users have had success on Python 3.13 by installing the Metal plugin from a Python 3.11 wheel and copying the `.dylib` into the 3.13 site-packages. This is unsupported and may break with TensorFlow updates. Prefer Option A if you want GPU soon.

---

**Summary:** For GPU on Apple Silicon today, use a **Python 3.11** env and **requirements-mac-gpu.txt** (Option A).
