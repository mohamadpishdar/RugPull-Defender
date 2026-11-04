# Running CRPWarner (W3)

CRPWarner is a static analyzer that looks for contract-related rug pulls. It works on EVM runtime bytecode (the compiled code that actually sits on the chain, not the Solidity source) and checks for three patterns: a hidden mint function, a leaking token, and a limiting sell order.

We use the public implementation (https://github.com/CRPWarner/RugPull) exactly as released, with no modifications.

This guide walks through four steps: set up the tools, compile the contracts, run CRPWarner, and collect the flags.

## 1. Install Souffle 2.3 and the Gigahorse functors (Ubuntu)

Start with the system packages:

```bash
sudo apt-get install -y libboost-all-dev libz3-dev mcpp libncurses-dev libsqlite3-dev zlib1g-dev
```

Souffle 2.3 needs `libffi7`, which newer Ubuntu releases no longer ship, so we install it by hand before Souffle itself:

```bash
wget http://archive.ubuntu.com/ubuntu/pool/main/libf/libffi/libffi7_3.3-4_amd64.deb
sudo dpkg -i libffi7_3.3-4_amd64.deb
wget https://github.com/souffle-lang/souffle/releases/download/2.3/x86_64-ubuntu-2004-souffle-2.3-Linux.deb
sudo dpkg --force-depends -i x86_64-ubuntu-2004-souffle-2.3-Linux.deb
souffle --version          # should print 2.3
```

Next, grab CRPWarner and build the Gigahorse functors:

```bash
git clone --depth 1 https://github.com/CRPWarner/RugPull.git
cd RugPull/gigahorse
rm -rf souffle-addon && git clone https://github.com/plast-lab/souffle-addon.git
cd souffle-addon && make && cd ..
```

Finally, run one example contract to check that everything works. The first run compiles the Datalog programs, so expect it to take 5 to 15 minutes. That's normal, and later runs are much faster.

```bash
python3 ./gigahorse.py -C ./clients/crpwarner.dl ../dataset/groundtruth/hex/0x0414D8C87b271266a5864329fb4932bBE19c0c49.hex
# The output should include "Hidden Mint Function:  True"
```

If you see that line, you're ready to go.

## 2. Compile the main contract of every project

```bash
pip install semantic_version pandas
python prepare_bytecode.py --clean ../data/flatten_source_code_noheader.zip \
    --obfuscated ../data/obfuscated_contracts_noheader.zip --out bytecode
```

A flattened file usually holds several contracts (the token itself plus helpers such as SafeMath), so the script has to decide which one to analyze. It picks the deployable contract with the largest runtime bytecode among those that no other contract in the file inherits from.

In our run, 957 of the 1,000 projects compiled in both conditions. For every project, the compiler version and the chosen main contract are written to `bytecode/log_{clean,obfuscated}.csv`. Our own copies are in `results/crpwarner/compile_log_*.csv`.

## 3. Run CRPWarner

```bash
./run_crpwarner.sh RugPull/gigahorse bytecode/clean      results_clean.json      12 300
./run_crpwarner.sh RugPull/gigahorse bytecode/obfuscated results_obfuscated.json 12 300
```

The last two arguments are the number of parallel jobs (12 here) and the time limit per contract in seconds (300, which is the tool's default). With 12 CPU cores, both conditions together take about seven hours, so this is a good one to start before lunch, or overnight.

**No powerful machine at hand?** `CRPWarner_rerun_colab.ipynb` covers steps 1, 3, and 4 on Google Colab, and it saves progress to Google Drive after every 100 contracts. If the session disconnects, you won't lose everything. Just run it again and it continues from where it stopped.

The notebook expects the output folder of step 2, renamed and zipped:

```bash
mv bytecode crp_input && zip -r crp_input.zip crp_input
```

Pick a runtime with plenty of CPU cores. The GPU isn't used.

## 4. Collect the flags

```bash
python collect_results.py --results results_clean.json --log bytecode/log_clean.csv \
    --out ../results/crpwarner/crpwarner_results_clean.csv
python collect_results.py --results results_obfuscated.json --log bytecode/log_obfuscated.csv \
    --out ../results/crpwarner/crpwarner_results_obfuscated.csv
```

A couple of things to keep in mind about the results:

- Projects without bytecode count as unflagged.
- Analyses that hit the time limit without raising a flag also count as unflagged.
- Inside the cascade, only the flags that were retained on the training folds are used. In every fold, that means leaking token and limiting sell order. You can see the details in `cascade/evaluate.py`.