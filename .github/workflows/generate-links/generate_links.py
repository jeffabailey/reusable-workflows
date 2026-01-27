#!/usr/bin/env python3
"""
Generate markdown links using GitHub Copilot Chat API.

This script processes markdown files from the Hugo published posts list and uses
GitHub Copilot to add internal links based on the provided prompt.

Requirements:
- GitHub Copilot CLI installed and authenticated
- GitHub token with appropriate permissions
- Python 3.11+

Note: GitHub Copilot CLI access requires:
- GitHub Copilot subscription
- Copilot CLI installed (separate from GitHub CLI)
- Appropriate API permissions
"""

import os
import sys
import subprocess
import csv
import io
import re
import argparse
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from difflib import unified_diff
from collections import defaultdict


def extract_prompt_from_hugo_content(content: str) -> str:
    """
    Extract prompt text from Hugo content format.
    
    Hugo prompt files have front matter and use {{% prompt-text %}} shortcode.
    This function extracts just the prompt content between the shortcode tags.
    
    Args:
        content: Full file content including front matter and shortcode
        
    Returns:
        Extracted prompt text, or original content if no shortcode found
    """
    # Try to find content between {{% prompt-text %}} and {{% /prompt-text %}}
    pattern = r'\{\{%\s*prompt-text[^%]*%\}\}(.*?)\{\{%\s*/prompt-text\s*%\}\}'
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        return match.group(1).strip()
    
    # If no shortcode found, try to strip front matter (content between --- markers)
    # and return the rest
    frontmatter_pattern = r'^---\s*\n.*?\n---\s*\n'
    content_without_frontmatter = re.sub(frontmatter_pattern, '', content, flags=re.DOTALL)
    
    # If content was significantly reduced, return the stripped version
    if len(content_without_frontmatter) < len(content) * 0.5:
        return content_without_frontmatter.strip()
    
    # Otherwise, return original content (might be plain markdown)
    return content.strip()


def parse_hugo_csv(hugo_list_csv: str, debug: bool = False) -> Dict[str, Dict]:
    """
    Parse Hugo list CSV to extract published posts.
    
    Returns a dictionary mapping file paths to post metadata.
    """
    published_posts = {}
    
    if not hugo_list_csv or not hugo_list_csv.strip():
        if debug:
            print("Hugo CSV is empty or not provided")
        return published_posts
    
    try:
        # Parse CSV
        reader = csv.DictReader(io.StringIO(hugo_list_csv))
        
        # Get column names for debugging
        if debug:
            print(f"CSV columns: {reader.fieldnames}")
            print(f"CSV content preview (first 500 chars): {hugo_list_csv[:500]}")
        
        row_count = 0
        for row in reader:
            row_count += 1
            if debug and row_count <= 3:
                print(f"Sample row {row_count}: {dict(row)}")
            
            # Check draft status - try multiple column name variations and formats
            draft_value = None
            for key in ['draft', 'Draft', 'DRAFT', 'isDraft', 'is_draft']:
                if key in row:
                    draft_value = row[key]
                    break
            
            # Also check if draft column exists but is empty (defaults to false in Hugo)
            if draft_value is None:
                # If no draft column found, assume published (Hugo default)
                draft_value = 'false'
            
            # Normalize draft value - could be "false", "False", "FALSE", "0", etc.
            draft_str = str(draft_value).strip().lower()
            is_published = draft_str in ['false', '0', 'no', 'n', '']
            
            if debug and row_count <= 3:
                print(f"  Draft value: {repr(draft_value)} -> {draft_str} -> published: {is_published}")
            
            # Only include published posts
            if is_published:
                path = row.get('path', '') or row.get('Path', '') or row.get('PATH', '')
                if path:
                    published_posts[path] = {
                        'path': path,
                        'permalink': row.get('permalink', '') or row.get('Permalink', '') or row.get('PERMALINK', ''),
                        'title': row.get('title', '') or row.get('Title', '') or row.get('TITLE', ''),
                        'draft': draft_str
                    }
        
        if debug:
            print(f"Processed {row_count} rows, found {len(published_posts)} published posts")
        
        # Limit to 10 published posts (as per workflow requirement)
        if len(published_posts) > 10:
            if debug:
                print(f"Limiting from {len(published_posts)} to 10 published posts")
            # Convert to list, take first 10, convert back to dict
            limited_posts = dict(list(published_posts.items())[:10])
            published_posts = limited_posts
    
    except Exception as e:
        print(f"⚠️  Warning: Could not parse Hugo CSV: {e}", file=sys.stderr)
        if debug:
            import traceback
            traceback.print_exc()
        print("   Continuing without published posts list...", file=sys.stderr)
    
    return published_posts


def find_published_files(content_folder: str, published_posts: Dict[str, Dict]) -> List[Path]:
    """
    Find markdown files that match published posts from Hugo list.
    
    Returns a list of Path objects for published post files.
    """
    content_path = Path(content_folder)
    if not content_path.exists():
        print(f"Error: Content folder {content_folder} does not exist", file=sys.stderr)
        sys.exit(1)
    
    # Find all markdown files
    all_md_files = list(content_path.rglob('*.md'))
    
    # If no published posts list provided, return empty list (don't process anything)
    # This ensures we only process files that are explicitly in the Hugo published list
    if not published_posts:
        return []
    
    # Build a set of normalized published post paths for quick lookup
    published_paths = set()
    for post_path, post_data in published_posts.items():
        # Normalize path
        norm_path = post_path.replace('\\', '/')
        published_paths.add(norm_path)
        # Also add without .md extension if present
        if norm_path.endswith('.md'):
            published_paths.add(norm_path[:-3])
        # Add directory path if it's an index.md
        if norm_path.endswith('/index.md'):
            published_paths.add(norm_path[:-9])  # Remove '/index.md'
    
    # Filter to only published posts
    published_files = []
    for md_file in all_md_files:
        # Skip excluded files
        if 'node_modules' in str(md_file) or '.git' in str(md_file):
            continue
        if md_file.name == 'notes.md' or md_file.name == 'links.md':
            continue
        
        # Check if this file matches a published post
        try:
            rel_path = md_file.relative_to(content_path)
            path_str = str(rel_path).replace('\\', '/')
            
            # Check various path formats
            matched = False
            
            # Direct match
            if path_str in published_paths:
                matched = True
            # Match without extension
            elif path_str.replace('.md', '') in published_paths:
                matched = True
            # Match directory to index.md
            elif md_file.name == 'index.md':
                parent_dir = str(rel_path.parent).replace('\\', '/')
                if parent_dir in published_paths or f"{parent_dir}/index.md" in published_paths:
                    matched = True
                # Also check if the post path ends with this directory
                for post_path in published_paths:
                    if post_path.endswith(parent_dir) or post_path.endswith(f"{parent_dir}/index.md"):
                        matched = True
                        break
            
            if matched:
                published_files.append(md_file)
        except Exception as e:
            # Skip files that can't be processed
            continue
    
    return published_files


def extract_links_from_diff(original: str, updated: str) -> List[str]:
    """
    Extract links that were added by comparing original and updated content.
    
    Returns a list of link descriptions.
    """
    links_added = []
    
    # Find markdown links: [text](url)
    markdown_link_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
    
    # Find Hugo shortcode links: {{< relref "path" >}} or [text]({{< relref "path" >}})
    hugo_shortcode_pattern = r'\[([^\]]+)\]\(\{\{<\s*relref\s+["\']([^"\']+)["\']\s*>\}\}\)'
    
    # Extract all links from both formats
    original_md_links = set(re.findall(markdown_link_pattern, original))
    updated_md_links = set(re.findall(markdown_link_pattern, updated))
    
    original_hugo_links = set(re.findall(hugo_shortcode_pattern, original))
    updated_hugo_links = set(re.findall(hugo_shortcode_pattern, updated))
    
    # Find new markdown links
    new_md_links = updated_md_links - original_md_links
    for text, url in new_md_links:
        links_added.append(f"  - [{text}]({url})")
    
    # Find new Hugo shortcode links
    new_hugo_links = updated_hugo_links - original_hugo_links
    for text, path in new_hugo_links:
        links_added.append(f"  - [{text}]({{{{< relref \"{path}\" >}}}})")
    
    # Also check for standalone relref shortcodes that might have been added
    standalone_relref_pattern = r'\{\{<\s*relref\s+["\']([^"\']+)["\']\s*>\}\}'
    original_standalone = set(re.findall(standalone_relref_pattern, original))
    updated_standalone = set(re.findall(standalone_relref_pattern, updated))
    new_standalone = updated_standalone - original_standalone
    for path in new_standalone:
        links_added.append(f"  - {{{{< relref \"{path}\" >}}}}")
    
    return links_added


def extract_all_links_from_content(content: str) -> List[Tuple[str, str, str]]:
    """
    Extract all links from markdown content.
    
    Returns a list of tuples: (link_text, link_url, link_type)
    where link_type is 'markdown', 'hugo_shortcode', or 'standalone_relref'
    """
    links = []
    
    # Find markdown links: [text](url)
    markdown_link_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
    for text, url in re.findall(markdown_link_pattern, content):
        links.append((text.strip(), url.strip(), 'markdown'))
    
    # Find Hugo shortcode links: [text]({{< relref "path" >}})
    hugo_shortcode_pattern = r'\[([^\]]+)\]\(\{\{<\s*relref\s+["\']([^"\']+)["\']\s*>\}\}\)'
    for text, path in re.findall(hugo_shortcode_pattern, content):
        links.append((text.strip(), path.strip(), 'hugo_shortcode'))
    
    # Find standalone relref shortcodes
    standalone_relref_pattern = r'\{\{<\s*relref\s+["\']([^"\']+)["\']\s*>\}\}'
    for path in re.findall(standalone_relref_pattern, content):
        links.append(('', path.strip(), 'standalone_relref'))
    
    return links


def build_link_graph(
    files_content: Dict[Path, str],
    published_posts: Dict[str, Dict],
    content_folder: str,
    debug: bool = False
) -> Tuple[Dict[str, Dict], List[Tuple[str, str]]]:
    """
    Build a graph of links from markdown files.
    
    Returns:
        - nodes: Dictionary mapping node_id to node data (label, url, type)
        - edges: List of tuples (source_id, target_id)
    """
    nodes = {}
    edges = []
    content_path = Path(content_folder)
    
    # Helper to get node ID from file path or URL
    def get_node_id(identifier: str, node_type: str = 'file') -> str:
        """Get or create a node ID."""
        if identifier not in nodes:
            nodes[identifier] = {
                'id': identifier,
                'label': identifier,
                'url': identifier,
                'type': node_type
            }
        return identifier
    
    # Process each file
    for file_path, content in files_content.items():
        try:
            # Get relative path for node ID
            rel_path = str(file_path.relative_to(content_path)) if file_path.is_relative_to(content_path) else str(file_path)
            source_id = get_node_id(rel_path, 'file')
            
            # Update node with file information
            nodes[source_id]['label'] = file_path.stem
            nodes[source_id]['file_path'] = str(file_path)
            
            # Extract all links from content
            links = extract_all_links_from_content(content)
            
            for link_text, link_url, link_type in links:
                # Normalize target URL/path
                target_id = link_url
                
                # For Hugo relref, try to resolve to actual file path
                if link_type in ('hugo_shortcode', 'standalone_relref'):
                    # Try to match against published posts
                    normalized_path = link_url.replace('\\', '/')
                    if normalized_path in published_posts:
                        post_data = published_posts[normalized_path]
                        target_id = post_data.get('permalink', normalized_path)
                        # Update node with post information
                        if target_id not in nodes:
                            nodes[target_id] = {
                                'id': target_id,
                                'label': post_data.get('title', normalized_path),
                                'url': post_data.get('permalink', normalized_path),
                                'type': 'post'
                            }
                        else:
                            nodes[target_id]['label'] = post_data.get('title', nodes[target_id]['label'])
                            nodes[target_id]['url'] = post_data.get('permalink', target_id)
                            nodes[target_id]['type'] = 'post'
                    else:
                        # Use path as-is
                        target_id = get_node_id(normalized_path, 'link')
                        nodes[target_id]['label'] = link_text if link_text else normalized_path
                
                # For markdown links, use URL as-is
                elif link_type == 'markdown':
                    target_id = get_node_id(link_url, 'link')
                    nodes[target_id]['label'] = link_text if link_text else link_url
                
                # Add edge
                edges.append((source_id, target_id))
        
        except Exception as e:
            if debug:
                print(f"⚠️  Error processing {file_path} for graph: {e}", file=sys.stderr)
            continue
    
    return nodes, edges


def save_csv_files(nodes: Dict[str, Dict], edges: List[Tuple[str, str]], base_path: str):
    """
    Save graph as separate node and edge CSV files for Cytoscape.
    
    Creates two files:
    - nodes.csv: id, label, url, type
    - edges.csv: source, target, interaction
    """
    try:
        base_name = os.path.splitext(base_path)[0]
        nodes_path = f"{base_name}_nodes.csv"
        edges_path = f"{base_name}_edges.csv"
        
        # Write nodes CSV file
        with open(nodes_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'label', 'url', 'type'])
            
            for node_id, node_data in sorted(nodes.items()):
                writer.writerow([
                    node_data.get('id', node_id),
                    node_data.get('label', node_id),
                    node_data.get('url', node_id),
                    node_data.get('type', 'unknown')
                ])
        
        # Write edges CSV file
        with open(edges_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['source', 'target', 'interaction'])
            
            for source_id, target_id in edges:
                writer.writerow([source_id, target_id, 'Directed'])
        
        print(f"💾 Saved CSV files:")
        print(f"   Nodes: {nodes_path} ({len(nodes)} nodes)")
        print(f"   Edges: {edges_path} ({len(edges)} edges)")
        
    except Exception as e:
        print(f"❌ Error saving CSV files: {e}", file=sys.stderr)


def save_cytoscape_json(nodes: Dict[str, Dict], edges: List[Tuple[str, str]], output_path: str):
    """
    Save graph in Cytoscape.js JSON format.
    
    Format:
    {
      "elements": {
        "nodes": [
          {"data": {"id": "...", "label": "...", "url": "...", "type": "..."}}
        ],
        "edges": [
          {"data": {"source": "...", "target": "...", "interaction": "Directed"}}
        ]
      }
    }
    """
    try:
        # Build nodes array
        nodes_array = []
        for node_id, node_data in sorted(nodes.items()):
            nodes_array.append({
                "data": {
                    "id": node_data.get('id', node_id),
                    "label": node_data.get('label', node_id),
                    "url": node_data.get('url', node_id),
                    "type": node_data.get('type', 'unknown')
                }
            })
        
        # Build edges array
        edges_array = []
        for source_id, target_id in edges:
            edges_array.append({
                "data": {
                    "source": source_id,
                    "target": target_id,
                    "interaction": "Directed"
                }
            })
        
        # Build Cytoscape JSON structure
        cytoscape_data = {
            "elements": {
                "nodes": nodes_array,
                "edges": edges_array
            }
        }
        
        # Write JSON file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cytoscape_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved Cytoscape JSON: {output_path}")
        print(f"   Nodes: {len(nodes_array)}, Edges: {len(edges_array)}")
        
    except Exception as e:
        print(f"❌ Error saving Cytoscape JSON: {e}", file=sys.stderr)


def get_github_copilot_response_batch(
    prompt: str,
    files_content: Dict[Path, str],
    github_token: str
) -> Optional[Dict[Path, str]]:
    """
    Get response from GitHub Copilot CLI for multiple files in a single call.
    
    Returns a dictionary mapping file paths to updated content.
    """
    # Build content section with all files
    files_section = "\n\n## Files to Process\n\n"
    file_list = []
    for file_path, content in files_content.items():
        file_list.append(str(file_path))
        # Limit content size to avoid token limits
        content_preview = content[:4000] if len(content) > 4000 else content
        files_section += f"### File: {file_path}\n\n```markdown\n{content_preview}\n```\n\n"
    
    file_list_str = "\n".join([f"- {fp}" for fp in file_list])
    
    # Construct the full prompt
    full_prompt = f"""{prompt}

## Files to Process

I need you to process {len(files_content)} markdown files and add internal links to each one. The files are:

{file_list_str}

{files_section}

## Instructions

1. Process ALL {len(files_content)} files listed above
2. For each file, add appropriate internal links to related published content
3. ONLY link to posts that are in the published posts list provided earlier (draft=false)
4. **CRITICAL: Return the COMPLETE file content for each file**, including:
   - The full front matter (YAML header between --- markers) if present
   - All original content
   - Only add new internal links - do NOT remove or modify existing content
   - Do NOT change the structure, formatting, or existing links
5. Return the updated content for EACH file using this exact format:

===FILE_START:{{file_path}}===
[COMPLETE updated markdown content for this file, including all front matter and original content]
===FILE_END:{{file_path}}===

For example, if processing file "blog/post/index.md", return:

===FILE_START:blog/post/index.md===
---
title: "Original Title"
date: 2026-01-01
---
[original content with new internal links added]
===FILE_END:blog/post/index.md===

**IMPORTANT**: 
- Process ALL files, not just one
- Use the exact file paths shown in the file list above
- Include the ===FILE_START: and ===FILE_END: markers for each file
- Return the COMPLETE file content, not just the changes
- Preserve all front matter, formatting, and existing content
- Only add links to published posts (draft=false from the Hugo list)

Please process all {len(files_content)} files and return the complete updated content with internal links added."""
    
    # Try using GitHub Copilot CLI
    try:
        clean_token = github_token.strip()
        subprocess_env = {**os.environ}
        subprocess_env['COPILOT_GITHUB_TOKEN'] = clean_token
        
        if not clean_token:
            print("Error: GitHub token is empty or invalid", file=sys.stderr)
            sys.exit(1)
        
        debug_flag = os.environ.get('DEBUG', 'false').lower() == 'true'
        
        # Determine the best way to pass the prompt based on size
        # Large prompts (>100KB) need to use stdin to avoid "Argument list too long" errors
        PROMPT_SIZE_LIMIT = 100 * 1024  # 100KB
        use_stdin = len(full_prompt.encode('utf-8')) > PROMPT_SIZE_LIMIT
        
        if use_stdin:
            # Write prompt to temporary file to avoid "Argument list too long" errors
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as tmp_file:
                tmp_file.write(full_prompt)
                tmp_prompt_file = tmp_file.name
        else:
            tmp_prompt_file = None
        
        try:
            if use_stdin:
                # Use stdin for large prompts
                copilot_cmd = [
                    'copilot',
                    '-p', '-',  # Read from stdin
                    '--allow-all-tools',
                    '--silent'
                ]
                
                if debug_flag:
                    print(f"Running copilot with COPILOT_GITHUB_TOKEN:")
                    print(f"  Processing {len(files_content)} files in a single call")
                    print(f"  Prompt length: {len(full_prompt)} characters (using stdin)")
                
                print(f"Calling copilot CLI to process {len(files_content)} files (this may take a moment)...", flush=True)
                
                # Read the prompt file and pass via stdin
                with open(tmp_prompt_file, 'r', encoding='utf-8') as prompt_file:
                    result = subprocess.run(
                        copilot_cmd,
                        stdin=prompt_file,
                        capture_output=True,
                        text=True,
                        timeout=600,  # 10 minute timeout for batch processing
                        env=subprocess_env
                    )
            else:
                # Use direct argument for smaller prompts
                copilot_cmd = [
                    'copilot',
                    '-p', full_prompt,
                    '--allow-all-tools',
                    '--silent'
                ]
                
                if debug_flag:
                    print(f"Running copilot with COPILOT_GITHUB_TOKEN:")
                    print(f"  Processing {len(files_content)} files in a single call")
                    print(f"  Prompt length: {len(full_prompt)} characters (using direct argument)")
                
                print(f"Calling copilot CLI to process {len(files_content)} files (this may take a moment)...", flush=True)
                
                result = subprocess.run(
                    copilot_cmd,
                    capture_output=True,
                    text=True,
                    timeout=600,  # 10 minute timeout for batch processing
                    env=subprocess_env
                )
            
            if debug_flag:
                print(f"Copilot CLI completed with return code: {result.returncode}")
                if result.stdout:
                    print(f"  stdout length: {len(result.stdout)} characters")
                if result.stderr:
                    print(f"  stderr length: {len(result.stderr)} characters")
        except subprocess.TimeoutExpired:
            print("❌ Copilot CLI timed out after 10 minutes", file=sys.stderr)
            print("   This may indicate too many files or the prompt is too long", file=sys.stderr)
            sys.exit(1)
        finally:
            # Clean up temp file if we created one
            if tmp_prompt_file:
                try:
                    os.unlink(tmp_prompt_file)
                except:
                    pass
        
        # Check for errors
        if result.stderr:
            error_msg = result.stderr.lower()
            if any(keyword in error_msg for keyword in ['no authentication', 'authentication information', 'not authenticated', 'login']):
                print(f"copilot CLI error: {result.stderr}", file=sys.stderr)
                print("❌ Copilot CLI authentication failed. Exiting immediately.", file=sys.stderr)
                sys.exit(1)
            if 'error:' in error_msg:
                print(f"copilot CLI error: {result.stderr}", file=sys.stderr)
                print(f"❌ Copilot CLI failed. Exiting immediately.", file=sys.stderr)
                sys.exit(1)
        
        if result.returncode != 0:
            if result.stderr:
                print(f"copilot CLI error: {result.stderr}", file=sys.stderr)
            print(f"❌ Copilot CLI failed with return code {result.returncode}. Exiting immediately.", file=sys.stderr)
            sys.exit(1)
        
        if result.returncode == 0 and result.stdout.strip():
            # Parse the response to extract updates for each file
            return parse_copilot_response(result.stdout.strip(), files_content.keys())
        
        print("❌ Copilot CLI returned unexpected result. Exiting immediately.", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Warning: GitHub Copilot CLI not found", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not use copilot CLI: {e}", file=sys.stderr)
    
    return None


def parse_copilot_response(response: str, file_paths: List[Path]) -> Dict[Path, str]:
    """
    Parse Copilot response to extract updated content for each file.
    
    Returns a dictionary mapping file paths to updated content.
    """
    updates = {}
    
    # Try multiple parsing strategies
    
    # Strategy 1: Structured format with FILE_START/FILE_END markers
    pattern1 = r'===FILE_START:(.+?)===\s*(.*?)\s*===FILE_END:\1==='
    matches1 = re.findall(pattern1, response, re.DOTALL)
    
    if matches1:
        for file_path_str, content in matches1:
            # Find matching file path
            for file_path in file_paths:
                file_path_normalized = str(file_path).replace('\\', '/')
                if (file_path_normalized == file_path_str or 
                    file_path.name in file_path_str or
                    str(file_path) in file_path_str):
                    updates[file_path] = content.strip()
                    break
    
    # Strategy 2: Look for file headers like "## File: path/to/file.md"
    if not updates:
        pattern2 = r'##\s*File:\s*(.+?)\n\n(.*?)(?=##\s*File:|$)'
        matches2 = re.findall(pattern2, response, re.DOTALL)
        
        if matches2:
            for file_path_str, content in matches2:
                for file_path in file_paths:
                    if file_path.name in file_path_str or str(file_path) in file_path_str:
                        updates[file_path] = content.strip()
                        break
    
    # Strategy 3: If only one file, check if response looks like complete file content
    if not updates and len(file_paths) == 1:
        # Only use this strategy if response looks like it contains front matter or is substantial
        response_stripped = response.strip()
        if response_stripped.startswith('---') or len(response_stripped) > 500:
            updates[file_paths[0]] = response_stripped
        else:
            print("⚠️  Warning: Response for single file doesn't look like complete content", file=sys.stderr)
            print(f"   Response length: {len(response_stripped)} chars", file=sys.stderr)
            print("   Skipping update to avoid overwriting with incomplete content", file=sys.stderr)
    
    # Strategy 4: If multiple files but no structure, try to split by common delimiters
    # This is risky, so we'll be more conservative
    if not updates and len(file_paths) > 1:
        # Try splitting by triple backticks or horizontal rules
        sections = re.split(r'```|---|\*\*\*', response)
        if len(sections) >= len(file_paths):
            for i, file_path in enumerate(file_paths):
                if i < len(sections):
                    section_content = sections[i].strip()
                    # Only use if it looks substantial (likely contains actual content)
                    if len(section_content) > 200:
                        updates[file_path] = section_content
    
    if not updates:
        print("⚠️  Warning: Could not parse structured response from Copilot", file=sys.stderr)
        print("   Response may not contain file markers or may be incomplete.", file=sys.stderr)
        print("   NOT updating files to avoid overwriting with incorrect content.", file=sys.stderr)
        print("   Please check the Copilot response format and try again.", file=sys.stderr)
        # Don't assign to first file as last resort - this is too risky
    
    return updates


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Generate markdown links using GitHub Copilot Chat API.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using environment variables (GitHub Actions workflow style)
  export COPILOT_GITHUB_TOKEN='your-token'
  export CONTENT_FOLDER='content/blog'
  export DEFAULT_PROMPT='$(cat content/prompts/internal-link-optimize.md)'
  python3 generate_links.py

  # Using command-line arguments
  python3 generate_links.py \\
    --token 'your-token' \\
    --content-folder 'content/blog' \\
    --prompt-file 'content/prompts/internal-link-optimize.md' \\
    --hugo-list-file 'hugo_list.csv'

  # Dry run (preview changes without modifying files)
  python3 generate_links.py --dry-run

Environment Variables:
  The script supports both command-line arguments and environment variables.
  Command-line arguments take precedence over environment variables.

  COPILOT_GITHUB_TOKEN    - GitHub token with Copilot API access (required)
  CONTENT_FOLDER          - Path to content folder (default: content/blog)
  CUSTOM_PROMPT           - Custom prompt text (overrides prompt file)
  DEFAULT_PROMPT          - Default prompt text (from prompt file)
                            If not set, script will try to read from
                            content/prompts/internal-link-optimize.md
  HUGO_LIST_FILE          - Path to Hugo list CSV file
                            If not provided, script will automatically
                            run 'hugo list all' to generate it
  HUGO_LIST_CSV           - Hugo list CSV content (alternative to file)
  DEBUG                   - Enable debug output (true/false)
  DRY_RUN                 - Preview changes without modifying files (true/false)
        """
    )
    
    parser.add_argument(
        '--token',
        dest='github_token',
        help='GitHub Copilot token (or use COPILOT_GITHUB_TOKEN env var)'
    )
    parser.add_argument(
        '--content-folder',
        dest='content_folder',
        help='Path to content folder (default: content/blog or CONTENT_FOLDER env var)'
    )
    parser.add_argument(
        '--prompt-file',
        dest='prompt_file',
        help='Path to prompt file (reads content and sets as DEFAULT_PROMPT). Default: content/prompts/internal-link-optimize.md'
    )
    parser.add_argument(
        '--custom-prompt',
        dest='custom_prompt',
        help='Custom prompt text (overrides prompt file, or use CUSTOM_PROMPT env var)'
    )
    parser.add_argument(
        '--hugo-list-file',
        dest='hugo_list_file',
        help='Path to Hugo list CSV file (or use HUGO_LIST_FILE env var). If not provided, script will automatically run "hugo list all"'
    )
    parser.add_argument(
        '--hugo-list-csv',
        dest='hugo_list_csv',
        help='Hugo list CSV content as string (or use HUGO_LIST_CSV env var)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug output (or use DEBUG=true env var)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying files (or use DRY_RUN=true env var)'
    )
    
    args = parser.parse_args()
    
    # Get values from command-line arguments or environment variables
    # Command-line arguments take precedence
    github_token = args.github_token or os.environ.get('COPILOT_GITHUB_TOKEN')
    content_folder = args.content_folder or os.environ.get('CONTENT_FOLDER', 'content/blog')
    custom_prompt = args.custom_prompt or os.environ.get('CUSTOM_PROMPT', '')
    default_prompt = os.environ.get('DEFAULT_PROMPT', '')
    hugo_list_file = args.hugo_list_file or os.environ.get('HUGO_LIST_FILE', '')
    hugo_list_csv = args.hugo_list_csv or os.environ.get('HUGO_LIST_CSV', '')
    debug = args.debug or os.environ.get('DEBUG', 'false').lower() == 'true'
    dry_run = args.dry_run or os.environ.get('DRY_RUN', 'false').lower() == 'true'
    
    # If prompt file is provided via command line, read it
    if args.prompt_file:
        try:
            with open(args.prompt_file, 'r', encoding='utf-8') as f:
                file_content = f.read()
            default_prompt = extract_prompt_from_hugo_content(file_content)
            if debug:
                print(f"Read prompt from file: {args.prompt_file} ({len(default_prompt)} characters)")
        except Exception as e:
            print(f"Error: Could not read prompt file {args.prompt_file}: {e}", file=sys.stderr)
            sys.exit(1)
    elif not default_prompt and not custom_prompt:
        # Try default prompt file location if no prompt is provided
        default_prompt_file = 'content/prompts/internal-link-optimize.md'
        if os.path.exists(default_prompt_file):
            try:
                with open(default_prompt_file, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                default_prompt = extract_prompt_from_hugo_content(file_content)
                if debug:
                    print(f"Read prompt from default file: {default_prompt_file} ({len(default_prompt)} characters)")
            except Exception as e:
                if debug:
                    print(f"Warning: Could not read default prompt file {default_prompt_file}: {e}", file=sys.stderr)
    
    # Read Hugo list from file if provided (avoids "Argument list too long" error)
    if hugo_list_file:
        try:
            with open(hugo_list_file, 'r', encoding='utf-8') as f:
                hugo_list_csv = f.read()
            if debug:
                print(f"Read Hugo list from file: {hugo_list_file} ({len(hugo_list_csv)} characters)")
        except Exception as e:
            print(f"⚠️  Warning: Could not read Hugo list file {hugo_list_file}: {e}", file=sys.stderr)
            print("   Falling back to HUGO_LIST_CSV environment variable if available", file=sys.stderr)
    
    # If no Hugo list provided, try to generate it automatically
    if not hugo_list_csv or not hugo_list_csv.strip():
        if debug:
            print("No Hugo list provided, attempting to generate it automatically...")
        
        # Try to find Hugo directory (look for config.toml or hugo.toml)
        hugo_dir = None
        current_dir = Path(os.getcwd())
        
        # Check current directory first
        if (current_dir / 'config.toml').exists() or (current_dir / 'hugo.toml').exists():
            hugo_dir = current_dir
        # Check parent directory (in case run from hugo/ subdirectory)
        elif (current_dir.parent / 'config.toml').exists() or (current_dir.parent / 'hugo.toml').exists():
            hugo_dir = current_dir.parent
        # Check if content_folder path gives us a clue
        elif content_folder:
            content_path = Path(content_folder)
            if content_path.exists():
                # Walk up to find Hugo root
                for parent in content_path.parents:
                    if (parent / 'config.toml').exists() or (parent / 'hugo.toml').exists():
                        hugo_dir = parent
                        break
        
        # Default to current directory if we can't find Hugo root
        if hugo_dir is None:
            hugo_dir = current_dir
            if debug:
                print(f"⚠️  Could not find Hugo root (config.toml or hugo.toml), using current directory: {hugo_dir}")
        else:
            if debug:
                print(f"Found Hugo root directory: {hugo_dir}")
        
        # Check if hugo command is available
        try:
            result = subprocess.run(
                ['hugo', 'list', 'all'],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(hugo_dir)  # Run from Hugo directory
            )
            
            if result.returncode == 0 and result.stdout.strip():
                hugo_list_csv = result.stdout
                total_lines = len(hugo_list_csv.splitlines())
                if debug:
                    print(f"✅ Generated Hugo list automatically ({total_lines} lines)")
                elif total_lines > 1:
                    print(f"✅ Generated Hugo list automatically ({total_lines} lines)")
            else:
                if debug:
                    print(f"⚠️  Hugo list command returned non-zero exit code: {result.returncode}", file=sys.stderr)
                    if result.stderr:
                        print(f"   Error: {result.stderr}", file=sys.stderr)
        except FileNotFoundError:
            if debug:
                print("⚠️  Hugo command not found - cannot generate Hugo list automatically", file=sys.stderr)
        except subprocess.TimeoutExpired:
            if debug:
                print("⚠️  Hugo list command timed out", file=sys.stderr)
        except Exception as e:
            if debug:
                print(f"⚠️  Could not generate Hugo list automatically: {e}", file=sys.stderr)
    
    if not github_token:
        print("Error: COPILOT_GITHUB_TOKEN environment variable is required", file=sys.stderr)
        print("  Please set the COPILOT_GITHUB_TOKEN secret in the workflow", file=sys.stderr)
        sys.exit(1)
    
    if debug:
        token_preview = f"{github_token[:8]}...{github_token[-4:]}" if len(github_token) > 12 else "***"
        print(f"Using token from COPILOT_GITHUB_TOKEN: {token_preview}")
        print(f"Token length: {len(github_token)} characters")
    
    # Extract prompt text from Hugo format if needed (for both custom and default)
    if custom_prompt:
        prompt = extract_prompt_from_hugo_content(custom_prompt)
    elif default_prompt:
        prompt = extract_prompt_from_hugo_content(default_prompt)
    else:
        prompt = ''
    
    if not prompt or prompt.strip() == "" or prompt == "No prompt file found":
        print("Error: No prompt provided (neither CUSTOM_PROMPT nor DEFAULT_PROMPT)", file=sys.stderr)
        print(f"  CUSTOM_PROMPT: {repr(custom_prompt)}", file=sys.stderr)
        print(f"  DEFAULT_PROMPT length: {len(default_prompt)}", file=sys.stderr)
        sys.exit(1)
    
    # Parse Hugo CSV to get published posts
    published_posts = parse_hugo_csv(hugo_list_csv, debug=debug)
    
    if debug:
        print(f"Content folder: {content_folder}")
        print(f"Prompt length: {len(prompt)} characters")
        print(f"Using custom prompt: {bool(custom_prompt)}")
        print(f"Dry run: {dry_run}")
        print(f"Found {len(published_posts)} published posts in Hugo list")
    
    # If Hugo list was provided but has no published posts, exit
    if hugo_list_csv and hugo_list_csv.strip() and len(published_posts) == 0:
        print("⚠️  Hugo list CSV was provided but contains no published posts (draft=false)")
        print("   Exiting - cannot process files without published posts list")
        sys.exit(0)
    
    # Enhance prompt with Hugo list data
    # Instead of including the full CSV (which can be huge), create a compact summary
    enhanced_prompt = prompt
    if published_posts:
        # Create a compact summary of published posts (path, title, permalink)
        # This avoids "Argument list too long" errors when passing to copilot CLI
        posts_summary_lines = []
        for post_path, post_data in list(published_posts.items())[:50]:  # Limit to 50 for prompt size
            title = post_data.get('title', '') or post_path
            permalink = post_data.get('permalink', '')
            posts_summary_lines.append(f"- {post_path} | {title} | {permalink}")
        
        posts_summary = "\n".join(posts_summary_lines)
        if len(published_posts) > 50:
            posts_summary += f"\n... and {len(published_posts) - 50} more published posts"
        
        enhanced_prompt = f"""{prompt}

## Published Blog Posts Available for Linking

The following is a list of published blog posts (draft=false) that you can link to:

Format: `path | title | permalink`

{posts_summary}

**CRITICAL: ONLY link to posts from this list.**
**CRITICAL: If a post is not in this list, DO NOT create a link to it.**
**CRITICAL: All posts in this list have `draft=false` and are published.**

When adding internal links, use the `permalink` value from this list for the link URL.
For Hugo sites, you can use either:
- Markdown links: `[text](permalink)`
- Hugo relref shortcodes: `{{{{< relref "path" >}}}}`

Only link to posts that are relevant and add value to the content.
"""
    
    # Find published files
    published_files = find_published_files(content_folder, published_posts)
    
    if debug:
        print(f"Found {len(published_files)} published markdown files to process")
    
    if not published_files:
        if published_posts:
            print("⚠️  Warning: Hugo list contains published posts but no matching files were found")
            print("   This may indicate a path mismatch between Hugo list and file system")
        else:
            print("No published markdown files found to process")
            print("   Either the Hugo list is empty or no files match the published posts")
        sys.exit(0)
    
    # Safety check: limit to reasonable number of files to avoid token/argument limits
    MAX_FILES = 10
    if len(published_files) > MAX_FILES:
        print(f"⚠️  Warning: Found {len(published_files)} files, limiting to {MAX_FILES} to avoid processing limits")
        published_files = published_files[:MAX_FILES]
        print(f"   Processing first {MAX_FILES} files only")
    
    # Read all files
    files_content = {}
    for file_path in published_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                files_content[file_path] = f.read()
        except Exception as e:
            print(f"⚠️  Warning: Could not read {file_path}: {e}", file=sys.stderr)
            continue
    
    if not files_content:
        print("No files could be read for processing")
        sys.exit(0)
    
    # Process all files in a single Copilot call
    print(f"\n📝 Processing {len(files_content)} files in a single batch...")
    updates = get_github_copilot_response_batch(enhanced_prompt, files_content, github_token)
    
    if updates is None:
        print("❌ Could not process files - Copilot API unavailable", file=sys.stderr)
        print("   This may require GitHub Copilot subscription and proper API access", file=sys.stderr)
        sys.exit(1)
    
    # Check if we got updates for all files
    files_with_updates = set(updates.keys())
    files_expected = set(files_content.keys())
    missing_files = files_expected - files_with_updates
    
    if missing_files:
        print(f"⚠️  Warning: Copilot did not return updates for {len(missing_files)} file(s):", file=sys.stderr)
        for missing_file in missing_files:
            print(f"   - {missing_file}", file=sys.stderr)
        print("   These files will be skipped.", file=sys.stderr)
    
    # Process updates and show what links were added
    changes_summary = []
    changes_made = 0
    
    print("\n" + "="*80)
    print("SUMMARY OF CHANGES - Links Added to Files")
    print("="*80 + "\n")
    
    for file_path in files_content.keys():
        if file_path not in updates:
            if debug:
                print(f"⚠️  {file_path} - No update received from Copilot")
            continue
            
        updated_content = updates[file_path]
        original_content = files_content.get(file_path, '')
        
        # Validation: Check if updated content looks valid
        # 1. Check if it contains the original front matter (Hugo files start with ---)
        original_has_frontmatter = original_content.strip().startswith('---')
        updated_has_frontmatter = updated_content.strip().startswith('---')
        
        if original_has_frontmatter and not updated_has_frontmatter:
            print(f"❌ {file_path} - Updated content missing front matter (YAML header)", file=sys.stderr)
            print("   Skipping update - this indicates a parsing error", file=sys.stderr)
            if debug:
                print(f"   Original starts with: {original_content[:100]}...", file=sys.stderr)
                print(f"   Updated starts with: {updated_content[:100]}...", file=sys.stderr)
            continue
        
        # 1b. If both have front matter, verify the front matter matches (title should be same)
        if original_has_frontmatter and updated_has_frontmatter:
            # Extract front matter from both
            original_frontmatter_match = re.match(r'^---\s*\n(.*?)\n---', original_content, re.DOTALL)
            updated_frontmatter_match = re.match(r'^---\s*\n(.*?)\n---', updated_content, re.DOTALL)
            
            if original_frontmatter_match and updated_frontmatter_match:
                original_frontmatter = original_frontmatter_match.group(1)
                updated_frontmatter = updated_frontmatter_match.group(1)
                
                # Extract title from both
                original_title_match = re.search(r'^title:\s*["\']?([^"\'\n]+)', original_frontmatter, re.MULTILINE)
                updated_title_match = re.search(r'^title:\s*["\']?([^"\'\n]+)', updated_frontmatter, re.MULTILINE)
                
                if original_title_match and updated_title_match:
                    original_title = original_title_match.group(1).strip()
                    updated_title = updated_title_match.group(1).strip()
                    
                    if original_title != updated_title:
                        print(f"❌ {file_path} - Front matter title changed (parsing error?)", file=sys.stderr)
                        print(f"   Original title: {original_title}", file=sys.stderr)
                        print(f"   Updated title: {updated_title}", file=sys.stderr)
                        print("   Skipping update - front matter should not change", file=sys.stderr)
                        continue
        
        # 2. Check if updated content is suspiciously short (likely parsing error)
        if len(updated_content) < len(original_content) * 0.5:
            print(f"⚠️  {file_path} - Updated content is significantly shorter than original", file=sys.stderr)
            print(f"   Original: {len(original_content)} chars, Updated: {len(updated_content)} chars", file=sys.stderr)
            print("   This may indicate a parsing error. Skipping update.", file=sys.stderr)
            if debug:
                print(f"   Original preview: {original_content[:200]}...", file=sys.stderr)
                print(f"   Updated preview: {updated_content[:200]}...", file=sys.stderr)
            continue
        
        # 3. Check if updated content is suspiciously long (likely includes extra content)
        if len(updated_content) > len(original_content) * 2:
            print(f"⚠️  {file_path} - Updated content is significantly longer than original", file=sys.stderr)
            print(f"   Original: {len(original_content)} chars, Updated: {len(updated_content)} chars", file=sys.stderr)
            print("   This may indicate a parsing error. Skipping update.", file=sys.stderr)
            if debug:
                print(f"   Original preview: {original_content[:200]}...", file=sys.stderr)
                print(f"   Updated preview: {updated_content[:200]}...", file=sys.stderr)
            continue
        
        if updated_content != original_content:
            # Extract links that were added
            links_added = extract_links_from_diff(original_content, updated_content)
            
            if links_added:
                changes_made += 1
                print(f"📄 {file_path}")
                print(f"   Added {len(links_added)} link(s):")
                for link in links_added:
                    print(link)
                print()
                
                changes_summary.append({
                    'file': file_path,
                    'links_count': len(links_added),
                    'links': links_added
                })
                
                # Write the updated content if not dry run
                if not dry_run:
                    try:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(updated_content)
                    except Exception as e:
                        print(f"❌ Error writing {file_path}: {e}", file=sys.stderr)
            else:
                if debug:
                    print(f"ℹ️  {file_path} - Content updated but no new links detected")
                    print("   Skipping write to avoid overwriting with potentially incorrect content")
        else:
            if debug:
                print(f"ℹ️  {file_path} - No changes needed")
    
    print("="*80)
    print(f"\n{'Would update' if dry_run else 'Updated'} {changes_made} file(s) with new internal links")
    
    # Build link graph and export to CSV and JSON
    if changes_made > 0 or len(updates) > 0:
        print("\n" + "="*80)
        print("GENERATING LINK GRAPH")
        print("="*80 + "\n")
        
        # Use updated content for graph building
        graph_files_content = {}
        for file_path in files_content.keys():
            if file_path in updates:
                graph_files_content[file_path] = updates[file_path]
            else:
                graph_files_content[file_path] = files_content[file_path]
        
        # Build graph from all links in processed files
        try:
            nodes, edges = build_link_graph(
                graph_files_content,
                published_posts,
                content_folder,
                debug=debug
            )
            
            if nodes and edges:
                # Determine output directory
                # Try to use the same directory as the script, or current working directory
                try:
                    script_dir = Path(__file__).parent
                except NameError:
                    script_dir = Path.cwd()
                
                output_dir = script_dir
                
                # Allow override via environment variable
                output_dir_env = os.environ.get('OUTPUT_DIR', '')
                if output_dir_env:
                    output_dir = Path(output_dir_env)
                
                output_dir.mkdir(parents=True, exist_ok=True)
                
                base_csv_path = str(output_dir / 'links_graph.csv')
                json_path = str(output_dir / 'links_graph.json')
                
                # Save CSV files
                if not dry_run:
                    save_csv_files(nodes, edges, base_csv_path)
                    
                    # Save Cytoscape JSON
                    save_cytoscape_json(nodes, edges, json_path)
                    
                    print(f"\n✅ Graph files saved to: {output_dir}")
                else:
                    print(f"📊 Would generate graph files:")
                    print(f"   CSV: {base_csv_path}_nodes.csv, {base_csv_path}_edges.csv")
                    print(f"   JSON: {json_path}")
            else:
                print("⚠️  No links found to build graph", file=sys.stderr)
        
        except Exception as e:
            print(f"⚠️  Warning: Could not generate graph files: {e}", file=sys.stderr)
            if debug:
                import traceback
                traceback.print_exc()
    
    if changes_made == 0:
        print("No changes were made to any files")
        sys.exit(0)
    
    # Exit successfully
    sys.exit(0)


if __name__ == '__main__':
    main()
