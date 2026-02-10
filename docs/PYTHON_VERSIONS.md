# Managing multiple Python versions

This project uses **Python 3.11** for the default setup (needed for `tensorflow-metal` on Apple Silicon). Here are two common ways to install and use 3.11 alongside other versions on macOS.

---

## Option 1: Homebrew

**Install Python 3.11**
```bash
brew install python@3.11
```

**Use it in this project**  
Homebrew does not add `python3.11` to your PATH by default. Either:

- **Temporary** (this terminal only):
  ```bash
  export PATH="/opt/homebrew/opt/python@3.11/bin:$PATH"   # Apple Silicon
  # or
  export PATH="/usr/local/opt/python@3.11/bin:$PATH"     # Intel Mac
  task setup
  ```

- **Permanent**: add the same `export` line to your `~/.zshrc` (or `~/.bash_profile`), then run `source ~/.zshrc` or open a new terminal.

Check that it’s used:
```bash
which python3.11   # should show Homebrew path
python3.11 --version   # Python 3.11.x
```

---

## Option 2: pyenv (manage many versions per directory)

**Install pyenv**
```bash
brew install pyenv
```

Add to `~/.zshrc` (or `~/.bash_profile`):
```bash
export PYENV_ROOT="$HOME/.pyenv"
[[ -d "$PYENV_ROOT/bin" ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
```
Then run `source ~/.zshrc` or open a new terminal.

**Install Python 3.11 and use it in this repo**
```bash
pyenv install 3.11.9
cd /path/to/your/cablelabs-3   # e.g. cd ~/workspace/nikhita/cablelabs-3
pyenv local 3.11.9
```
(You must run `pyenv install 3.11.9` first; otherwise `pyenv local 3.11.9` will say "version not installed".)

Now in this directory, `python` and `python3` point to 3.11.9. Run:
```bash
task setup
```
**If `task setup` says "python: executable file not found":** the shell may not have pyenv in PATH. Run `eval "$(pyenv init -)"` in that terminal (or open a new terminal so your shell loads pyenv from `~/.zshrc`), then run `task setup` again.

**Other directories** keep using your system (or global) Python until you run `pyenv local` there. To set 3.11 everywhere: `pyenv global 3.11.9`.

---

## Overriding without installing 3.11

If you want to use your current Python (e.g. 3.13) and skip GPU support:

```bash
PYTHON=python3 task setup
```

That creates the venv with whatever `python3` is on your PATH. The ML notebooks will run on CPU only (no `tensorflow-metal` on 3.13).
