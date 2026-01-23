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
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from difflib import unified_diff


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
4. Return the updated content for EACH file using this exact format:

===FILE_START:{{file_path}}===
[updated markdown content for this file]
===FILE_END:{{file_path}}===

For example, if processing file "blog/post/index.md", return:

===FILE_START:blog/post/index.md===
[updated content here]
===FILE_END:blog/post/index.md===

**IMPORTANT**: 
- Process ALL files, not just one
- Use the exact file paths shown in the file list above
- Include the ===FILE_START: and ===FILE_END: markers for each file
- Only add links to published posts (draft=false from the Hugo list)

Please process all {len(files_content)} files and return the updated content with internal links added."""
    
    # Try using GitHub Copilot CLI
    try:
        clean_token = github_token.strip()
        subprocess_env = {**os.environ}
        subprocess_env['COPILOT_GITHUB_TOKEN'] = clean_token
        
        if not clean_token:
            print("Error: GitHub token is empty or invalid", file=sys.stderr)
            sys.exit(1)
        
        debug_flag = os.environ.get('DEBUG', 'false').lower() == 'true'
        
        copilot_cmd = [
            'env',
            f'COPILOT_GITHUB_TOKEN={clean_token}',
            'copilot',
            '-p', full_prompt,
            '--allow-all-tools',
            '--silent'
        ]
        
        if debug_flag:
            print(f"Running copilot with COPILOT_GITHUB_TOKEN:")
            print(f"  Processing {len(files_content)} files in a single call")
            print(f"  Prompt length: {len(full_prompt)} characters")
        
        print(f"Calling copilot CLI to process {len(files_content)} files (this may take a moment)...", flush=True)
        
        try:
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
    
    # Strategy 3: If only one file, assume entire response is for that file
    if not updates and len(file_paths) == 1:
        updates[file_paths[0]] = response.strip()
    
    # Strategy 4: If multiple files but no structure, try to split by common delimiters
    if not updates and len(file_paths) > 1:
        # Try splitting by triple backticks or horizontal rules
        sections = re.split(r'```|---|\*\*\*', response)
        if len(sections) >= len(file_paths):
            for i, file_path in enumerate(file_paths):
                if i < len(sections):
                    updates[file_path] = sections[i].strip()
    
    if not updates:
        print("⚠️  Warning: Could not parse structured response from Copilot", file=sys.stderr)
        print("   Response may not contain file markers. Attempting to use entire response...", file=sys.stderr)
        # Last resort: assign entire response to first file (not ideal but better than failing)
        if file_paths:
            updates[file_paths[0]] = response.strip()
    
    return updates


def main():
    """Main entry point for the script."""
    # Get environment variables
    github_token = os.environ.get('COPILOT_GITHUB_TOKEN')
    content_folder = os.environ.get('CONTENT_FOLDER', 'content/blog')
    custom_prompt = os.environ.get('CUSTOM_PROMPT', '')
    default_prompt = os.environ.get('DEFAULT_PROMPT', '')
    hugo_list_csv = os.environ.get('HUGO_LIST_CSV', '')
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    dry_run = os.environ.get('DRY_RUN', 'false').lower() == 'true'
    
    if not github_token:
        print("Error: COPILOT_GITHUB_TOKEN environment variable is required", file=sys.stderr)
        print("  Please set the COPILOT_GITHUB_TOKEN secret in the workflow", file=sys.stderr)
        sys.exit(1)
    
    if debug:
        token_preview = f"{github_token[:8]}...{github_token[-4:]}" if len(github_token) > 12 else "***"
        print(f"Using token from COPILOT_GITHUB_TOKEN: {token_preview}")
        print(f"Token length: {len(github_token)} characters")
    
    # Use custom prompt if provided, otherwise use default
    prompt = custom_prompt if custom_prompt else default_prompt
    
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
    enhanced_prompt = prompt
    if hugo_list_csv and hugo_list_csv.strip():
        enhanced_prompt = f"""{prompt}

## Published Blog Posts Data

The following CSV data contains all published blog posts from `hugo list all`:

```
{hugo_list_csv}
```

**CRITICAL: ONLY link to posts from this list that have `draft=false`.**
**CRITICAL: If a post is not in this list, DO NOT create a link to it.**

Use this data to identify which posts are published and available for internal linking. Filter by:
- `draft=false` (only published posts)
- Posts in the `content/blog` directory
- Exclude `_index.md` files

When adding internal links, reference posts from this list using their `path` or `permalink` values.
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
        else:
            if debug:
                print(f"ℹ️  {file_path} - No changes needed")
    
    print("="*80)
    print(f"\n{'Would update' if dry_run else 'Updated'} {changes_made} file(s) with new internal links")
    
    if changes_made == 0:
        print("No changes were made to any files")
        sys.exit(0)
    
    # Exit successfully
    sys.exit(0)


if __name__ == '__main__':
    main()
