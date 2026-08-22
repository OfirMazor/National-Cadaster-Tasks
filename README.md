# National Cadaster Tasks (MNCDB)

Python toolset backing the ArcGIS Pro **Task items** (*"אשפי בנק"ל"*) used to edit Israel's National Cadaster Database — a branch-versioned **Parcel Fabric** hosted on ArcGIS Enterprise.

Each step an operator clicks in an ArcGIS Pro Task maps to a *script tool* in [Project/NCDBCustomTools.atbx](Project/NCDBCustomTools.atbx), which executes one Python entry point in [ScriptsAndTools/](ScriptsAndTools/). The scripts drive the whole editing lifecycle: validating a process, opening a private branch version, loading and retiring cadastral features, running QA, and posting the result back to `sde.DEFAULT` and to the CMS.

> **This is not a standalone application.** Virtually every module depends on `arcpy` and on `ArcGISProject("current")` — an open `.aprx` with a specific set of Hebrew-named layers. Nothing here runs from a plain shell.

---

## Table of Contents

- [Who this is for](#who-this-is-for)
- [Features](#features)
- [How it fits together](#how-it-fits-together)
- [Prerequisites](#prerequisites)
- [Repository layout](#repository-layout)
- [Installation & Deployment](#installation--deployment)
- [Usage](#usage)
- [Configuration](#configuration)
- [Key invariants](#key-invariants)
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

## Features

**The three-phase editing pipeline**

- **Start Task** — runs a per-task validation set, creates the process "shelf" folder, opens a branch version, displays the process data, loads in-process features into the fabric, retires the superseded ones, and activates the record.
- **Update Attributes** — recalculates attributes on the currently *active record*; also owns retirement, block reshaping, record building and status updates used by the other phases.
- **Evaluation** — QA sweep over a chosen extent: topology rules, gaps & overlaps, adjacent points, disconnected points, deviated parcel areas, redundant vertices, volumetric (3D) overlaps. Each check that finds something adds its own result layer.
- **Completion** — diffs every edited layer into per-layer `Differences.xlsx` workbooks, reconciles and posts the version, updates status, and notifies the CMS.

**Six supported task types** (`Utils/TypeHints.py::TaskType`)

`ImproveCurrentCadaster` · `RetireAndCreateCadaster` · `RetireAndCreateCadaster3D` · `CreateNewCadaster` · `ImproveNewCadaster` · `FreeEdit`

**Standalone assistants** ([ScriptsAndTools/Assistants/](ScriptsAndTools/Assistants/))

Reinitialize project · Display process data · Print last parcel number · Process record info · Retire points or fronts · Locate unmatched source points · Update blocks geometry from active parcels · Update selected fronts attributes

**Cross-cutting**

- Three-environment switch (Development / Test / Production) from a single config class.
- Durable per-process "shelf" so later steps read back state instead of re-querying SDE.
- All operator feedback via `arcpy.AddMessage` / `AddWarning` / `AddError`, with timestamps and phase headers; tabular output via `Helpers.AddTabularMessage`.

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

## Prerequisites

**Software**

- **ArcGIS Pro 3.3 or later**, with its bundled Python environment (`arcpy`).
  The codebase uses PEP 604 unions (`str | None`) in annotations that are evaluated at import, so **Python 3.10 is the hard floor**.
- **Parcel Fabric** licensing and a **Standard/Advanced** ArcGIS Pro license.
- The **3D Analyst** extension for the 3D task family (checked out at runtime by `Helpers`).

**Python packages** — all ship with the ArcGIS Pro conda environment; no `pip install` step exists or is needed:

`arcpy` · `arcgis` · `pandas` · `numpy` · `requests`

**Infrastructure access**

- ArcGIS Enterprise portal and the `NationalCadasterEditors` feature services (fabric map + in-process map + Version Management Server).
- SDE connection files for the target environment, on the SDE share.
- Read/write access to the `Parcel Fabric` network share (scripts, layers, templates and the process library all live there).
- Reachable CMS endpoint for status callbacks.
- An organization **VDI account** — Completion asks for those credentials and appends the domain itself.

---

## Repository layout

| Path | Contents |
| --- | --- |
| [ScriptsAndTools/](ScriptsAndTools/) | All Python. Top-level files are script-tool entry points. |
| [ScriptsAndTools/Utils/](ScriptsAndTools/Utils/) | Shared modules — `Configs`, `Helpers`, `Validations`, `UpdateAttributes`, `QA`, `VersionManagement`, `Reports`, `TypeHints`, plus the New Cadaster variants. |
| [ScriptsAndTools/Assistants/](ScriptsAndTools/Assistants/) | Standalone helper tools (run from a subdirectory — see the `set_path` note below). |
| [Project/](Project/) | The live ArcGIS Pro project: `Project.aprx`, `Project.gdb`, `NCDBCustomTools.atbx`. |
| [Tasks/](Tasks/) | Exported `.esriTasks` Task items, versioned by filename (`MNCDB_Tasks_1.7` … `1.8.2`). |
| [Layers/](Layers/) | `.lyrx` files loaded at runtime — process groups and QA result layers. |
| [Templates/](Templates/) | `Versions.csv` seed, `Templates.gdb`, `TransferGeometryExpression.lxp`. |
| [Library/](Library/) | Sample/real per-process shelf data. **Not code.** |
| `docs/` | Changelog & tutorials page, deployment checklist (Hebrew), configuration deck. |
| `Bugs/` | Minimal reproductions of ArcGIS Pro platform bugs, kept for Esri support cases. |

---

## Installation & Deployment

There is **no build, no test suite and no package manifest**. "Installation" means placing the tree on the right share and repointing the project at it.

### 1. Get the code

```bash
git clone <repo-url> NationalCadasterTasks
cd NationalCadasterTasks
```

### 2. Create your configuration

`ScriptsAndTools/Utils/Configs.py` is **git-ignored** — it holds internal host names, IP addresses and share paths. Create it from the checked-in template:

```bash
cp ScriptsAndTools/Utils/Configs.example.py ScriptsAndTools/Utils/Configs.py
```

Then fill in every `<placeholder>` and set `Environment` to the environment this copy serves. See [Configuration](#configuration).

### 3. Deploy to an environment

The full checklist (Hebrew) lives at `docs/Instructions-update test environment.txt`. In summary:

1. Copy the folder tree to `\\<file-server>\<share>\Parcel Fabric\<Env>Environment\`.
2. Flip `CNFG.Environment` in that copy's `Configs.py`.
3. Re-import the Task item from [Tasks/](Tasks/) into the `.aprx`.
4. Repoint **every** script tool's `tool.script.execute.link` to the new UNC path.
5. Repoint **every** layer's feature-service URL in the `.aprx`.

> ⚠️ Flipping `CNFG.Environment` is **not sufficient on its own** — steps 3–5 are mandatory, and two known gaps bite here (see [Configuration](#configuration)).

### 4. Verify

Verification happens **by running the script tool inside ArcGIS Pro** against the target environment — not from a terminal. Run one Start Task end to end and confirm the shelf folder, the branch version and the activated record all appear.

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

## Key invariants

Read these before your first change — they are load-bearing.

- **Branch versioning.** All edits happen in a per-process branch version `<ProcessName>_<user>_<n>` created by `VersionManagement.open_version`. `close_version` reconciles with `FAVOR_EDIT_VERSION` / `NO_ABORT` and posts to `sde.DEFAULT`. **Never edit `sde.DEFAULT` directly.**
- **The shelf.** Each process gets `Library/<ProcessName with / → _>/` holding `RecordGUID.txt`, `RetiredParcels2D.txt`, `RetiredBlocks.txt`, `Versions.csv`, `EarlyConflictsReport.xlsx`, `Modifications/`. These are the durable side-channel later steps read back — the record GUID alone has 20+ read sites. Writing them is not optional bookkeeping.
- **Layers are addressed by Hebrew display name** in the active map (`get_layer('חלקות')`), never by path. Renaming a layer in the `.aprx` breaks the scripts.
- **Editing sessions.** Feature edits are wrapped in `start_editing(ENV.workspace)` / `stop_editing(editor)`. `ENV.preserveGlobalIds = False` is set deliberately.
- **Coded domains.** Statuses, record types and process types are integers with Hebrew meanings, commented inline (e.g. `RecordType in [1, 2, 11]  # [תצ"ר, תצ"ר בשטח לא מוסדר, תמ"ר]`). **Keep the inline comment when you touch such a literal.**
- **Two parallel stacks.** The New Cadaster family duplicates helper names from the classic one — `Utils/NewCadasterHelpers.py` / `Utils/ValidationsNewCadaster.py` vs `Utils/Helpers.py` / `Utils/Validations.py`. They are **not interchangeable**; check which module a symbol comes from before editing.
- **Output.** Use `arcpy.AddMessage` / `AddWarning` / `AddError` — never `print`. Convention: `f'{timestamp()} | ✔️ ...'`, with a `f'\n ⭕ <phase>:'` header per phase.

---

## Contributing

1. Work on a feature branch; `main` is the release branch.
2. Never commit `ScriptsAndTools/Utils/Configs.py` — it is git-ignored for a reason. Update `Configs.example.py` instead when you add a key.
3. If you change a tool's parameters, update `tool.content` inside the `.atbx` **and** the script's `__main__` block in the same commit.
4. Verify by running the affected script tool in ArcGIS Pro against Development. There is no CLI test path.
5. Shipping a Task version: export a new `.esriTasks` into [Tasks/](Tasks/) and update the changelog section of the docs page.

---

## License

No license file is present in this repository. This is internal software for the National Cadaster Database; treat it as **proprietary and all rights reserved** unless the project owner states otherwise.

If this repository should carry an explicit license, add a `LICENSE` file and update this section.
