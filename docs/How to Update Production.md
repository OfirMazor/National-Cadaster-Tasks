# Environment Update Instructions

Complete guide for updating the National Cadaster Tasks from Development environment to Production environment.

---

## Step-by-Step Instructions

### Step 1: Reinitialize the ArcGIS Pro Project in Development Environment

**Why:** Ensures a clean state before deploying to the target environment.

**How:**
1. Open the National Cadaster project in ArcGIS Pro (Development environment)
2. Run the Reinitialize GP tool in the project toolbox
3. Click the save bookmark that pans the active map towards the Survey of Israel area.
4. Remove layers/tables that aren't relevant to the project.
5. Clear tool execution history (Analysis -> History -> Select all -> **X** button to delete)
6. Repeat steps 1-5 on the Scene Editing map object ('סצנת עריכה')

---

### Step 2: Backup Tasks Items

Export the updated tasks as a file to the `Tasks` folder and publish to the Development portal.

**Why:** Ensures the target environment has the latest task definitions.

**How:**
1. In ArcGIS Pro, go to the Share panel
2. Select **Tasks** 
3. Save the exported file to the `Tasks/` directory with an appropriate version number (e.g., `MNCDB_Tasks_1.8.2.esriTasks`). Note the filename for later reference
5. Publish the tasks to the Development portal at the NationalCadasterEditors group.

---

### Step 3: Copy Environment Folder Structure

Copy the updated files from Development to Production.

**Why:** Ensures all scripts, files, and dependencies are updated.

**How:**
1. Navigate to `\\mapi_shares\MNCDB\Parcel Fabric\ProductionEnvironment`
2. Delete the following folders from the current Production folder: 
   - Layers
   - Project
   - ScriptsAndTools
   - Tasks
   - Templates
   - **DO NOT** delete the Library Folder !
3. Copy the folders from issue 2 above (with their content) from `DevelopmentEnvironment/` into the Production Folder. Do not copy the Library folder. 
4. Verify that all files copied successfully

---

### Step 4: Update Environment Configuration

Update the `Configs.py` file in the production environment to point to the correct environment.

**Why:** Ensures all scripts use the correct database connections, URLs, and folder paths.

**How:**
1. Open `ScriptsAndTools/Utils/Configs.py` and simply replace the value of Environment from "Development" to "Production" (`Environment: EnviType = Production`)
5. Save the file.

---

### Step 5: Re-Import Production Tasks in ArcGIS Pro Project

Re-import the tasks into the ArcGIS Pro project in the Production environment from the updated `Tasks` folder.

**Why:** Updates the project with the exported task definitions from Step 3.

**How:**
1. Open the ArcGIS Pro project (`.aprx`) in the production environment
2. Open the **Tasks** panel
3. Select **Import Tasks**.
4. Navigate to the `Tasks/` folder and select the exported task file from Step 3
6. Click **Import**
7. Verify the tasks imported successfully

---

### Step 6: Update Script Tools Paths

For each script-tool in the project toolbox, update the script file path to point to the production environment's script folder.

**Why:** Ensures script-tools execute the correct scripts from the target environment.

**How:**
1. In ArcGIS Pro, open the **Catalog** pane
2. Open the **NCDBCustomTools** toolbox to view all the tools
4. For each script-tool:
   - Right-click the tool to open its properties
   - Navigate to the **Execution** tab on the left
   - Update the path from:
     - `\\mapi_shares\MNCDB\Parcel Fabric\DevelopmentEnvironment\ScriptsAndTools\...`
     - To: `\\mapi_shares\MNCDB\Parcel Fabric\ProductionEnvironment\ScriptsAndTools\...`
   - Click **OK** to save
5. Repeat for all script-tools in the toolbox
6. Save the production project.

---

### Step 7: Update Layer Feature Service URLs

For each layer in the ArcGIS Pro project, update the layer source URL to point to the production portal's feature service.

**Why:** Ensures layers display data from the production environment database.

**How:**
1. In ArcGIS Pro, open the **Contents** pane (showing all layers)
2. Right-click the map item and select `Update Data Sources`, a data source manager window will open.
2. For each layer that needs updating:
   - Set the correct feature service path in the New Path column on the right. Repeat for the layers on the Scene.
   - Click **Validate and Apply** to save.
3. Exit the Data Sources window and save the project.

---

### Step 8: Verify Project Options and Paths

Verify that all folder paths in the project options are configured correctly for the production environment.

**Why:** Ensures the project can locate all required folders and resources.

**How:**
1. In ArcGIS Pro, go to **Project → Options → Current Settings**
2. Check the folder paths for:
   - Working directory
   - Database connections
   - Scratch folder
   - Any custom paths defined in the project
3. Update any paths that still reference the Development environment
4. Change them to reference the production environment instead
5. Click **OK** and save the project.

---

### Step 9: Verify TaskHistory Table Configuration

Ensure the TaskHistory table is properly configured in the ArcGIS Pro project for the production environment.

**Why:** Ensures the project can track task execution history correctly.

**How:**
1. Navigate to **Project → Options → Tasks**
2. Verify that the TaskHistory table is configured and points to the correct location

---

### Step 10: Commit Updated Files to GitHub

Push the updated files to the GitHub repository.

**Why:** Maintains version control and creates a record of the deployment.

**How:**
1. Open the project [repository](https://github.com/OfirMazor/National-Cadaster-Tasks)
2. Load necessary files to the Production branch and commit the changes.
3. Verify the push succeeded on GitHub.

---

### Step 11: Document the changes in the National Cadaster Tasks web page

Write and describe the fixes, new features and changes in the new version of the tasks.

**Why:** Documenting these changes helps users and developers understand and trace what changed and when.

**How:**
1. Open the html file in the docs folder `index.html`.
2. Change the `Current Version` value
3. Add information regarding the Fixes, Improvements, or Other changes.
