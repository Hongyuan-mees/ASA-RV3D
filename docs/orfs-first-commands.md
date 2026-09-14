# ORFS First Commands

Date: 2026-09-14

This checklist is for the first server-side OpenROAD-flow-scripts setup steps.

Run one block at a time. After each block, check the output before continuing.

Do not install ORFS, build OpenROAD, or run the Ibex flow until the earlier checks pass.

## Source References

- ORFS repository: https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts
- ORFS documentation: https://openroad-flow-scripts.readthedocs.io/
- ORFS Docker build documentation: https://openroad-flow-scripts.readthedocs.io/en/latest/user/BuildWithDocker.html

The ORFS docs recommend Docker for new users because it avoids many host dependency issues. The Docker build documentation also notes that `build_openroad.sh` can use the host CPU count unless the thread count is restricted.

## Important Copy Rule

When copying commands into a terminal, copy only the plain command text.

Do not paste Markdown link syntax such as:

```text
[https://github.com/example/repo.git](https://github.com/example/repo.git)
```

Use only:

```text
https://github.com/example/repo.git
```

## Step 0: Enter The Approved Workspace

Replace `<approved-user-workspace>` with the server workspace assigned for this project.

```bash
cd <approved-user-workspace>
pwd
```

Expected:

- `pwd` prints the approved project workspace.
- Stop if the path is outside the approved workspace.

## Step 1: Sync This Project Repository

```bash
cd RV3D_Public
git pull
git status --short --branch
```

Expected:

- `git pull` succeeds.
- `git status` shows `main...origin/main`.
- Stop if there are local uncommitted changes on the server.

## Step 2: Check Basic Server State

```bash
cd <approved-user-workspace>
df -h .
docker --version
git --version
```

Expected:

- disk free space is not critically low
- Docker is available
- Git is available

Stop before downloading if disk space is unexpectedly low.

## Step 3: Confirm ORFS Is Not Already Present

```bash
cd <approved-user-workspace>
ls -ld openroad-flow-scripts
```

Expected if ORFS is not present yet:

```text
ls: cannot access 'openroad-flow-scripts': No such file or directory
```

If the directory already exists, do not overwrite it. Inspect it first:

```bash
cd openroad-flow-scripts
git remote -v
git status --short --branch
```

Stop and report the output before deciding whether to reuse it.

## Step 4: Clone ORFS

Only run this if Step 3 showed that `openroad-flow-scripts` does not already exist.

```bash
cd <approved-user-workspace>
git clone --recursive https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts.git openroad-flow-scripts
```

Expected:

- clone completes without submodule errors
- no files are created inside `RV3D_Public`

Stop if:

- the clone fails
- submodules fail
- the checkout becomes unexpectedly large
- the command asks to write outside the approved workspace

## Step 5: Record ORFS Version

```bash
cd <approved-user-workspace>/openroad-flow-scripts
git rev-parse HEAD
git status --short --branch
git submodule status --recursive | sed -n '1,20p'
```

Expected:

- `git rev-parse HEAD` prints the ORFS commit ID
- working tree is clean
- submodule status prints public dependency commit IDs

Save the ORFS commit ID in project notes later.

## Step 6: Inspect The Ibex Example

```bash
cd <approved-user-workspace>/openroad-flow-scripts
ls flow/designs/sky130hd/ibex
sed -n '1,120p' flow/designs/sky130hd/ibex/config.mk
ls flow/designs/src/ibex_sv
```

Expected:

- the Ibex config directory exists
- `config.mk` is readable
- the public Ibex SystemVerilog source directory exists

Stop if the Ibex path is missing or materially different from expected.

## Step 7: Do Not Run The Flow Yet

At this point, stop and send back:

- ORFS clone result
- ORFS commit ID
- `git status --short --branch` from the ORFS checkout
- `ls flow/designs/sky130hd/ibex`
- the first 120 lines of `flow/designs/sky130hd/ibex/config.mk`

After that, the next decision is whether to use:

- official Docker shell flow
- prebuilt binaries
- source build with explicit thread limit

Do not run these yet:

```bash
./build_openroad.sh
./build_openroad.sh --threads 8
cd flow && util/docker_shell make DESIGN_CONFIG=./designs/sky130hd/ibex/config.mk
```

These commands are for a later step after clone inspection.
