# 🗺️ National Cadaster Tasks (MNCDB)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![ArcGIS Pro 3.3+](https://img.shields.io/badge/ArcGIS%20Pro-3.3%2B-green?logo=esri&logoColor=white)](https://www.esri.com/)
[![License](https://img.shields.io/badge/License-Proprietary-red)](./LICENSE)
[![Environments](https://img.shields.io/badge/Environments-Dev%20%7C%20Test%20%7C%20Prod-orange)](./ScriptsAndTools/Utils/Configs.py)

**Python toolset backing the ArcGIS Pro Task items** (*"אשפי בנק"ל"*) used to edit Israel's National Cadaster Database — a branch-versioned **Parcel Fabric** hosted on ArcGIS Enterprise.

Each step an operator clicks in an ArcGIS Pro Task maps to a *script tool* in [Project/NCDBCustomTools.atbx](Project/NCDBCustomTools.atbx), which executes one Python entry point in [ScriptsAndTools/](ScriptsAndTools/). The scripts drive the whole editing lifecycle: validating a process, opening a private branch version, loading and retiring cadastral features, running QA, and posting the result back to `sde.DEFAULT` and to the CMS.

> ⚠️ **Not a standalone application.** Virtually every module depends on `arcpy` and on `ArcGISProject("current")` — an open `.aprx` with a specific set of Hebrew-named layers. Nothing here runs from a plain shell.

---

## 📖 Table of Contents

- [Who this is for](#who-this-is-for)
- [Features](#-features)
- [How it fits together](#how-it-fits-together)
- [Prerequisites](#-prerequisites)
- [Repository layout](#-repository-layout)
- [Installation & Deployment](#-installation--deployment)
- [Usage](#usage)
- [Configuration](#configuration)
- [Key invariants](#-key-invariants)
- [Contributing](#contributing)
- [License](#license)

---

## Who this is for

| Audience | What they need from this repo |
| --- | --- |
| **Cadastral operators / surveyors** | Run the Tasks inside ArcGIS Pro. You do not need this repo — see the Task wizard and the changelog page. |
| **GIS developers maintaining the toolset** | Edit the scripts, keep tool-parameter contracts intact, ship a new Task version. |
| **Deployment / release engineers** | Promote a build from Development → Test → Production across the network shares. |

---

## ✨ Features

### 📊 The Three-Phase Editing Pipeline

| Phase | Description |
|-------|-------------|
| **🚀 Start Task** | Validates process, creates shelf folder, opens branch version, displays data, loads & retires features, activates record |
| **✏️ Update Attributes** | Recalculates attributes on active record; owns retirement, reshaping, building, status updates |
| **🔍 Evaluation** | QA sweep: topology, gaps & overlaps, adjacent/disconnected points, deviated areas, redundant vertices, 3D overlaps |
| **✅ Completion** | Diffs layers → `Differences.xlsx`, reconciles & posts version, updates status, notifies CMS |

### 📋 Six Supported Task Types

```
🏗️ ImproveCurrentCadaster
🔄 RetireAndCreateCadaster
🌐 RetireAndCreateCadaster3D
✨ CreateNewCadaster
🎨 ImproveNewCadaster
🎯 FreeEdit
```

### 🛠️ Standalone Assistants

Eight helper tools for process management, data inspection, and bulk operations:

- 🔧 Reinitialize project
- 📍 Display process data
- 🔢 Print last parcel number
- 📄 Process record info
- 🗑️ Retire points or fronts
- 🔎 Locate unmatched source points
- 📐 Update blocks geometry from active parcels
- 🏷️ Update selected fronts attributes

### 🔗 Cross-Cutting Features

- 🌍 **Three-environment switch** (Development / Test / Production) from a single config class
- 📚 **Durable per-process "shelf"** — later steps read back state instead of re-querying SDE
- 📢 **Structured operator feedback** via `arcpy.AddMessage` / `AddWarning` / `AddError` with timestamps & phase headers

---

## How it fits together

```
ArcGIS Pro Task item (.esriTasks)
        │  step → tool
        ▼
NCDBCustomTools.atbx  ──  <ToolName>.tool/
        │                   ├── tool.content              (ordered parameters, domains, defaults)
        │                   ├── tool.content.rc           (Hebrew UI labels)
        │                   ├── tool.script.execute.link  (UNC path to the .py)
        │                   └── tool.script.validate.py   (optional ToolValidator)
        ▼
ScriptsAndTools/<EntryPoint>.py     →  GetParameter(i) → one orchestrating function
        ▼
ScriptsAndTools/Utils/*.py          →  Helpers, Validations, UpdateAttributes, QA,
                                        VersionManagement, Reports, Configs
        ▼
Parcel Fabric (branch version)  ·  Shelf folder  ·  CMS endpoint
```

> **Tool names do not match script filenames.** `StartTaskImprove.tool` → `StartTaskImproveCurrentCadaster.py`; both `StartTaskCreateNew.tool` and `StartTaskImproveNew.tool` → `StartTaskNewCadaster.py`.

---

## 📋 Prerequisites

### 💻 Software

- ✅ **ArcGIS Pro 3.3+** with bundled Python (`arcpy`)
  - PEP 604 unions (`str | None`) require **Python 3.10 minimum**
- ✅ **Parcel Fabric** licensing + **Standard/Advanced** ArcGIS Pro license
- ✅ **3D Analyst** extension for 3D task family (auto-checked at runtime)

### 📦 Python Packages

All included with ArcGIS Pro — no `pip install` needed:

```
arcpy  ·  arcgis  ·  pandas  ·  numpy  ·  requests
```

### 🏢 Infrastructure Access

| Component | Purpose |
|-----------|---------|
| **ArcGIS Enterprise portal** | Portal authentication & feature services |
| **NationalCadasterEditors** feature services | Fabric map, in-process map, Version Management Server |
| **SDE connection files** | Connection to Parcel Fabric for target environment |
| **Parcel Fabric network share** | Scripts, layers, templates, process library |
| **CMS endpoint** | Status callbacks & process updates |
| **VDI account** | Organization credentials for Completion phase |

---

## 📂 Repository Layout

```
📦 NationalCadasterTasks/
├── 🐍 ScriptsAndTools/                          All Python entry points & shared modules
│   ├── Start/Update/Evaluation/Completion.py    Main pipeline scripts
│   ├── Utils/                                   Helpers, Configs, QA, VersionManagement, etc.
│   └── Assistants/                              Standalone tools (process mgmt, QA, data updates)
├── 🎨 Project/                                  Live ArcGIS Pro project
│   ├── Project.aprx                             The project file (requires Hebrew layers)
│   ├── Project.gdb                              Home geodatabase
│   └── NCDBCustomTools.atbx                     Toolbox with script-tool definitions
├── 📋 Tasks/                                    Exported .esriTasks items (versioned)
├── 🗺️ Layers/                                    .lyrx files (process groups & QA layers)
├── 📐 Templates/                                Seeds & templates for new processes
├── 📚 Library/                                  Sample per-process shelf data (not code)
├── 📖 docs/                                     Changelog, tutorials, deployment checklist (Hebrew)
├── 🐛 Bugs/                                     Minimal reproductions of ArcGIS Pro bugs
└── 📄 README.md                                 This file
```

| Directory | Purpose |
|-----------|---------|
| [ScriptsAndTools/](ScriptsAndTools/) | **Python source.** Top-level `.py` files are script-tool entry points. |
| [ScriptsAndTools/Utils/](ScriptsAndTools/Utils/) | **Shared modules:** Configs, Helpers, Validations, UpdateAttributes, QA, VersionManagement, Reports, TypeHints + New Cadaster variants. |
| [ScriptsAndTools/Assistants/](ScriptsAndTools/Assistants/) | **Helper tools** — run from subdirectory; see `set_path` bootstrap below. |
| [Project/](Project/) | **ArcGIS Pro project:** `.aprx`, `.gdb`, `.atbx` with tool definitions. |
| [Tasks/](Tasks/) | **Versioned Task items** (`MNCDB_Tasks_1.7` → `1.8.2`). |
| [Layers/](Layers/) | **Layer definitions** (process groups + QA result layers). |
| [Templates/](Templates/) | **Seed data:** `Versions.csv`, `Templates.gdb`, expression files. |
| [Library/](Library/) | **Sample shelf data.** Not code — real/test process artifacts. |
| [docs/](docs/) | **Documentation** (Hebrew): deployment checklist, configuration, changelog. |

---

## 🚀 Installation & Deployment

> 📌 **No build, no test suite, no package manifest.** "Installation" = placing the tree on the right share + repointing the project.

### Step 1️⃣ — Clone the Repository

```bash
git clone <repo-url> NationalCadasterTasks
cd NationalCadasterTasks
```

### Step 2️⃣ — Configure for Your Environment

Create your environment-specific config from the template:

```bash
cp ScriptsAndTools/Utils/Configs.example.py ScriptsAndTools/Utils/Configs.py
```

Then fill in **every placeholder** and set `Environment` to your target (Development / Test / Production). See [Configuration](#configuration) for details.

### Step 3️⃣ — Deploy to Network Share

Copy the entire folder tree to your network location:
```
\\<file-server>\<share>\Parcel Fabric\<Env>Environment\
```

Then follow these **critical repointing steps**:

1. ✅ Flip `CNFG.Environment` in your copy's `Configs.py`
2. ✅ Re-import the Task item from [Tasks/](Tasks/) into the `.aprx`
3. ✅ Repoint **every** script tool's `tool.script.execute.link` to the new UNC path
4. ✅ Repoint **every** layer's feature-service URL in the `.aprx`

> 🚨 **Critical:** Simply flipping `CNFG.Environment` is **NOT sufficient**. Steps 2–4 are mandatory or tools will fail silently.

### Step 4️⃣ — Verify in ArcGIS Pro

**No CLI test path exists.** Verification is manual:

1. Open `Project.aprx` in ArcGIS Pro
2. Run one **Start Task** end-to-end against your target environment
3. Confirm these appear: shelf folder, branch version, activated record

---

## Usage

### For operators — the normal path

Open `Project.aprx`, open the Tasks pane, pick the task matching your process, and walk the steps:

```
1. Start Task            →  validations, branch version, load + retire, activate record
2. Update Attributes     →  recalculate attributes on the active record
3. Evaluation            →  QA checks over Full map / Record / Current display
4. Completion            →  diff, reconcile & post, update status, notify CMS
```

The process name is normally derived from the `.aprx` filename. When the CMS is down, tick **Independent** and type the process name explicitly.

### For developers — inspecting the parameter contract

Parameter order is **positional and bound to the toolbox**, not to the Python signature. The `.atbx` is a zip archive and is inspectable without ArcGIS Pro:

```bash
# List every <ToolName>.tool/ folder
unzip -l "Project/NCDBCustomTools.atbx"

# Read the ordered "params" block — these are the GetParameter(i) indices
unzip -p "Project/NCDBCustomTools.atbx" "StartTaskRetireAndCreate.tool/tool.content"
```

Every entry point follows the same shape:

```python
# ScriptsAndTools/StartTaskRetireAndCreateCadaster.py
if __name__ == "__main__":
    start_record_editing(
        Independent=GetParameter(0),
        ProcessName=GetParameterAsText(1),
        Report=GetParameter(2),
    )
```

```python
# ScriptsAndTools/Completion.py
if __name__ == "__main__":
    Completion(
        user_name=GetParameterAsText(0),   # organization VDI account, no domain
        password=GetParameterAsText(1),
    )
```

**Reordering, inserting or renaming a parameter silently breaks the tool.** Change `tool.content` and the script together.

### Assistants must bootstrap `sys.path`

Scripts under `Assistants/` run from a subdirectory, so they start with:

```python
from set_path import add_parent_to_sys_path
add_parent_to_sys_path(__file__)
```

Top-level scripts import `Utils.*` directly — `ScriptsAndTools/` is the working root.

---

## Configuration

[ScriptsAndTools/Utils/Configs.py](ScriptsAndTools/Utils/Configs.py) is the **single switch**. Setting one field drives every folder path, SDE connection, portal URL, feature service, CMS endpoint and default version GUID:

```python
class CNFG:
    Environment: EnviType = 'Development'   # 'Development' | 'Test' | 'Production'
    OwnerName:   str      = 'PF.'
```

Every environment-dependent value is a dict keyed by environment and resolved through `Environment`:

```python
CMS_url_mapping: dict[EnviType, str] = {
    "Development": "http://<dev-host>:7777/manage/api/...",
    "Test":        "http://<test-host>:7777/manage/api/...",
    "Production":  "http://<prod-host>:7777/manage/api/...",
}
CMS_url: str = CMS_url_mapping[Environment]
```

**When adding a new environment-dependent value, add it as a `dict[EnviType, ...]` keyed the same way — never hardcode it.** Then mirror the new key into `Configs.example.py` so the template stays complete.

### Known configuration gaps

| Gap | Effect |
| --- | --- |
| `default_version_guids['Test']` is `None` *(TODO)* | Anything reading the default version GUID fails in Test. |
| Uneven `.lyrx` coverage | Only `NewCadasterLayers` and `RetireAndCreateProcessGroup` exist for all three environments; `RetireAndCreateProcess3DGroup` is Development-only; the rest have no `_Test` variant. A missing file surfaces as a runtime failure in `display_process_data`. |
| New Cadaster validations | The two New Cadaster entries in `Validations.validation_set` are still stubs (Signed-in check only). |

Layer files come in two flavours: **environment-suffixed** process groups (`<Group>_{CNFG.Environment}.lyrx`) and **environment-agnostic** QA/result layers (`AdjacentPoints`, `Conflicts`, `GapsAndOverlaps`, …).

---

## ⚡ Key Invariants

**Read these before your first change — they are load-bearing.**

| Invariant | Rule | Why It Matters |
|-----------|------|----------------|
| **🔀 Branch Versioning** | All edits in per-process branch `<ProcessName>_<user>_<n>` created by `VersionManagement.open_version`. Reconcile with `FAVOR_EDIT_VERSION` / `NO_ABORT`, post to `sde.DEFAULT`. | ❌ Never edit `sde.DEFAULT` directly — breaks the fabric |
| **📚 The Shelf** | Each process gets `Library/<ProcessName>/` with `RecordGUID.txt`, `RetiredParcels2D.txt`, `RetiredBlocks.txt`, `Versions.csv`, `EarlyConflictsReport.xlsx`, `Modifications/`. This is the durable side-channel. | Writing these is **not optional** — 20+ read sites depend on RecordGUID alone |
| **🏷️ Layer Names** | Address layers by Hebrew display name in active map: `get_layer('חלקות')`, **never by path**. | Renaming a layer in `.aprx` silently breaks scripts |
| **✏️ Editing Sessions** | Wrap all feature edits in `start_editing(ENV.workspace)` / `stop_editing(editor)`. `ENV.preserveGlobalIds = False` is intentional. | Ensures transaction safety & consistent GlobalID handling |
| **🔢 Coded Domains** | Statuses, record types, process types are integers with Hebrew meanings. Always add inline comment: `RecordType in [1, 2, 11]  # [תצ"ר, ...]` | Prevents silent semantic bugs when domains change |
| **📦 Dual Stacks** | New Cadaster duplicates helper names: `NewCadasterHelpers.py` + `NewCadasterValidations.py` vs `Helpers.py` + `Validations.py`. **Not interchangeable.** | Wrong import = quiet runtime failures; always verify module |
| **📢 User Output** | Use `arcpy.AddMessage` / `AddWarning` / `AddError` only. Never `print`. Format: `f'{timestamp()} \| ✔️ ...'` with phase headers. | Terminal output never reaches the operator; arcpy messages appear in task UI |

---

## 🤝 Contributing

**Before you start:**

1. ✅ Work on a **feature branch** — `main` is the release branch
2. ❌ **Never commit** `ScriptsAndTools/Utils/Configs.py` (git-ignored). Update `Configs.example.py` when adding keys
3. 🔗 **Tool parameters are positional & bound to `.atbx`** — update both `tool.content` *and* the script's `__main__` block in the same commit
4. 🧪 **Verify in ArcGIS Pro** against Development — no CLI test path exists
5. 🚀 **Shipping a Task version:** Export `.esriTasks` to [Tasks/](Tasks/) and update the docs changelog

> 💡 **Pro tip:** Use `unzip -p "Project/NCDBCustomTools.atbx" "<ToolName>.tool/tool.content"` to inspect the parameter contract without opening ArcGIS Pro.

---

## 📜 License

This repository contains **internal software for the National Cadaster Database**.

- **No explicit license file** is present
- Treat as **proprietary — all rights reserved** unless the project owner states otherwise
- To add an explicit license, create a `LICENSE` file and update this section

---

## 🔗 Quick Links

- 📊 **Configuration:** [Configs.py](ScriptsAndTools/Utils/Configs.py) — the single source of truth for environments
- 📖 **Deployment guide** (Hebrew): [docs/Instructions-update test environment.txt](docs/Instructions-update%20test%20environment.txt)
- 🎯 **Task types:** [TypeHints.py::TaskType](ScriptsAndTools/Utils/TypeHints.py#L40)
- 🛠️ **Toolbox definition:** [Project/NCDBCustomTools.atbx](Project/NCDBCustomTools.atbx)
- 📋 **Task versions:** [Tasks/](Tasks/) — `MNCDB_Tasks_1.7` → `1.8.2`

---

<div align="center">

**Made with 🗺️ for cadastral editing in ArcGIS Pro**

</div>
