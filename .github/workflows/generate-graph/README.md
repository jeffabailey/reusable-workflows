# Website Graph Generator

This script crawls a website and generates a graph of internal links in Cytoscape-compatible CSV format.

## Output Files

The script generates two CSV files:
- `graph_nodes.csv` - Node attributes (id, label, url, depth)
- `graph_edges.csv` - Edge list (source, target, interaction)

## Importing into Cytoscape

Follow these steps to import the graph and visualize it with labels:

### Step 1: Import Nodes

1. Open Cytoscape
2. Go to **File** → **Import** → **Network** → **From File...**
3. Select `graph_nodes.csv`
4. In the import dialog:
   - **Select a key column for Network**: Choose `id` from the dropdown
   - **Select a key column for Network**: This should be set to `id` (the URL column)
   - Click **OK**

### Step 2: Import Edges

1. Go to **File** → **Import** → **Network** → **From File...**
2. Select `graph_edges.csv`
3. In the import dialog:
   - **Select a key column for Source Node**: Choose `source` from the dropdown
   - **Select a key column for Target Node**: Choose `target` from the dropdown
   - **Select a key column for Network**: Choose `source` (or any column, this is less critical)
   - Make sure "Import as Edge Table" is selected
   - Click **OK**

### Step 3: Display Labels

1. In the **Control Panel** (left side), go to the **Style** tab
2. Find the **Label** property
3. Click on the **Map** column next to Label
4. In the mapping dialog:
   - **Column**: Select `label` from the dropdown
   - Click **OK`
5. The node labels (page titles) should now be visible on the graph

### Step 4: Adjust Layout (Optional)

1. Go to **Layout** menu
2. Choose a layout algorithm:
   - **yFiles Layouts** → **Organic** (good for general graphs)
   - **Prefuse Force Directed** (good for large graphs)
   - **Circular Layout** (good for smaller graphs)

### Tips

- **Node colors by depth**: In the Style tab, map the `depth` column to the **Fill Color** property to color-code nodes by crawl depth
- **Node size by connections**: Map the **Degree** property to **Size** to make highly connected nodes larger
- **Filter nodes**: Use **Select** → **Nodes** → **By Column Value** to filter specific nodes
- **Export image**: Use **File** → **Export** → **Network View as Image** to save the visualization
