set -euo pipefail

python_formula="python@3.14"
python_bin="python3.14"

clean=0
for arg in "$@"; do
  case "$arg" in
    --clean)
      clean=1
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

if [[ "$clean" -eq 1 ]]; then
  rm -rf dist build .venv bin/abcm2ps bin/abc2abc bin/abc2midi bin/midi2abc
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "build.sh requires Homebrew to provide abcm2ps, abcmidi, uv, and Python. Install it from https://brew.sh and try again." >&2
  exit 1
fi

brew install abcm2ps abcmidi

if ! command -v uv >/dev/null 2>&1; then
  brew install uv
fi

if ! command -v "$python_bin" >/dev/null 2>&1; then
  brew install "$python_formula"
fi

if [[ ! -d .venv ]]; then
  uv venv --python "$python_bin" .venv
  uv pip install -r requirements.txt
fi

mkdir -p bin
cp "$(brew --prefix abcm2ps)/bin/abcm2ps" bin/
for tool in abc2abc abc2midi midi2abc; do
  cp "$(brew --prefix abcmidi)/bin/$tool" bin/
done

.venv/bin/python setup.py py2app

for dir in locale/*/; do
   file=$(basename "$dir")
   mkdir "dist/EasyABC.app/Contents/Resources/$file.lproj"
done
mkdir "dist/EasyABC.app/Contents/Resources/English.lproj"   
#force to have executable binary as py2app remove the executable flag
chmod +x dist/EasyABC.app/Contents/Resources/bin/*
