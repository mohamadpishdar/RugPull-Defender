# CRPWarner (RugPull) – Local Run Guide (manual souffle-addon copy method)

This workflow is for Ubuntu 22.04 x86_64 with prerequisites already installed (`build-essential`, `cmake`, `python3`, `libboost-all-dev`, `libz3-dev`, `souffle 2.4.1`).

## 0. if not

```bash
sudo apt update
sudo apt install -y build-essential cmake python3 python3-pip libboost-all-dev libz3-dev git curl
sudo apt install -y souffle
souffle --version
```

---

## 1. Clone the repos

```bash
# RugPull (your fork or upstream)
git clone https://github.com/CRPWarner/RugPull.git

# Also clone gigahorse-toolchain separately, with all its submodules
git clone --recursive https://github.com/nevillegrech/gigahorse-toolchain.git
```

---

## 2. Copy souffle-addon into RugPull

```bash
cp -r gigahorse-toolchain/souffle-addon/* RugPull/gigahorse/souffle-addon/
```

---

## 3. Build souffle-addon inside RugPull

```bash
cd RugPull/gigahorse/souffle-addon

make clean || true
WORD_SIZE=$(souffle --version | sed -n '3p' | cut -c12,13)
make WORD_SIZE="$WORD_SIZE"

ls -l libfunctors.so   # should exist
```

---

## 4. Set LD_LIBRARY_PATH

```bash
SO_ADDON_ABS="$(pwd)"
export LD_LIBRARY_PATH="$SO_ADDON_ABS:${LD_LIBRARY_PATH:-}"

# (optional, to persist across shells)
echo "export LD_LIBRARY_PATH=\"$SO_ADDON_ABS:\$LD_LIBRARY_PATH\"" >> ~/.bashrc
```

---

## 5. Sanity check compilation

From `RugPull/gigahorse`:

```bash
mkdir -p cache
souffle -I clientlib -I logic -I clients -w \
  -c clients/crpwarner.dl \
  -o cache/crpwarner.dl_compiled \
  2> preproc.err

[ -s preproc.err ] && sed -n '1,120p' preproc.err
```

- **Success:** `cache/crpwarner.dl_compiled` exists and no fatal errors.

---

## 6. Run CRPWarner

```bash
cd RugPull/gigahorse

python3 ./gigahorse.py --debug \
  -C ./clients/crpwarner.dl \
  ../dataset/groundtruth/hex/<contract_hash>.hex
```

Example:

```bash
python3 ./gigahorse.py --debug -C ./clients/crpwarner.dl \
  ../dataset/groundtruth/hex/0x0414D8C87b271266a5864329fb4932bBE19c0c49.hex
```

---

## 7. Troubleshooting (short list)

- **`libfunctors.so` not found** → Rebuild in `RugPull/gigahorse/souffle-addon` and re-export `LD_LIBRARY_PATH`.
- **`preproc.err` not empty / missing includes** → Run the `souffle -I ... -c clients/crpwarner.dl` line and read the first missing include in `preproc.err`.
- **Wrong toolchain commit** → Re-clone gigahorse-toolchain recursively and re-copy `souffle-addon`.
