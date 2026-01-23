#!/usr/bin/env python3
"""
Generate markdown links using GitHub Copilot Chat API.

This script processes markdown files in a specified directory and uses
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
import json
from pathlib import Path
from typing import List, Optional


def get_github_copilot_response(prompt: str, content: str, github_token: str) -> Optional[str]:
    """
    Get response from GitHub Copilot CLI.
    
    This function uses the dedicated Copilot CLI in non-interactive mode,
    or falls back to GitHub API if available.
    """
    import requests
    
    # Construct the full prompt
    full_prompt = f"""{prompt}

Please analyze the following markdown content and add appropriate internal links to related content. 
Only add links that are relevant and improve the content. Maintain the existing structure and style.

Content:
{content[:8000]}

Please provide the updated markdown with internal links added. Return only the updated markdown content."""
    
    # Try using GitHub Copilot CLI
    try:
        # Use copilot CLI in non-interactive mode with prompt
        # Note: This requires GitHub Copilot subscription and the Copilot CLI
        # --allow-all-tools is required for non-interactive mode
        # --silent outputs only the agent response (useful for scripting)
        # Copilot CLI checks for tokens in this order: COPILOT_GITHUB_TOKEN, GH_TOKEN, GITHUB_TOKEN
        # Set all three to ensure authentication works
        subprocess_env = {**os.environ}
        subprocess_env['GITHUB_TOKEN'] = github_token
        subprocess_env['GH_TOKEN'] = github_token
        subprocess_env['COPILOT_GITHUB_TOKEN'] = github_token
        
        result = subprocess.run(
            ['copilot', '-p', full_prompt, '--allow-all-tools', '--silent'],
            capture_output=True,
            text=True,
            timeout=300,  # Increased timeout for Copilot CLI
            env=subprocess_env
        )
        
        # Check for errors first - fail immediately if any error is detected
        if result.stderr:
            error_msg = result.stderr.lower()
            # Check for authentication errors specifically
            if any(keyword in error_msg for keyword in ['no authentication', 'authentication information', 'not authenticated', 'login']):
                print(f"copilot CLI error: {result.stderr}", file=sys.stderr)
                print("❌ Copilot CLI authentication failed. Exiting immediately.", file=sys.stderr)
                sys.exit(1)
            # Check for any other errors in stderr
            if 'error:' in error_msg:
                print(f"copilot CLI error: {result.stderr}", file=sys.stderr)
                print(f"❌ Copilot CLI failed. Exiting immediately.", file=sys.stderr)
                sys.exit(1)
        
        # Fail immediately for any non-zero return code
        if result.returncode != 0:
            if result.stderr:
                print(f"copilot CLI error: {result.stderr}", file=sys.stderr)
            print(f"❌ Copilot CLI failed with return code {result.returncode}. Exiting immediately.", file=sys.stderr)
            sys.exit(1)
        
        # Only return if we have valid output
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        
        # If we get here, something unexpected happened
        print("❌ Copilot CLI returned unexpected result. Exiting immediately.", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Warning: GitHub Copilot CLI not found. Trying GitHub API...", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("Warning: GitHub Copilot CLI request timed out", file=sys.stderr)
    except subprocess.SubprocessError as e:
        print(f"Warning: Could not use copilot CLI: {e}", file=sys.stderr)
    
    # Fallback: Try GitHub Copilot Chat API directly
    # Note: This endpoint may require special permissions
    try:
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28'
        }
        
        # GitHub Copilot Chat API endpoint (if available)
        # This is a placeholder - the actual endpoint may differ
        # You may need to use GitHub's Copilot Chat API when it becomes available
        # For now, we'll return None to indicate we need a different approach
        
        # Alternative: Use GitHub's API to create a completion request
        # This would require the Copilot Chat API which may not be publicly available yet
        
    except Exception as e:
        print(f"Warning: Could not use GitHub API: {e}", file=sys.stderr)
    
    return None


def process_markdown_file(
    file_path: Path,
    prompt: str,
    github_token: str,
    dry_run: bool = False
) -> bool:
    """
    Process a single markdown file to add internal links.
    
    Returns True if changes were made, False otherwise.
    """
    try:
        # Read the file
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        # Get updated content from GitHub Copilot
        updated_content = get_github_copilot_response(
            prompt,
            original_content,
            github_token
        )
        
        if updated_content is None:
            print(f"⚠️  Could not process {file_path} - Copilot API unavailable")
            print(f"   This may require GitHub Copilot subscription and proper API access")
            return False
        
        # Check if content changed
        if updated_content != original_content:
            if not dry_run:
                # Write the updated content
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
                print(f"✅ Updated {file_path}")
            else:
                print(f"🔍 Would update {file_path} (dry run)")
            return True
        else:
            print(f"ℹ️  No changes needed for {file_path}")
            return False
            
    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}", file=sys.stderr)
        return False


def main():
    """Main entry point for the script."""
    # Get environment variables
    # Copilot CLI checks for tokens in this order: COPILOT_GITHUB_TOKEN, GH_TOKEN, GITHUB_TOKEN
    github_token = (
        os.environ.get('COPILOT_GITHUB_TOKEN') or
        os.environ.get('GH_TOKEN') or
        os.environ.get('GITHUB_TOKEN')
    )
    content_folder = os.environ.get('CONTENT_FOLDER', 'content/blog')
    custom_prompt = os.environ.get('CUSTOM_PROMPT', '')
    default_prompt = os.environ.get('DEFAULT_PROMPT', '')
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    dry_run = os.environ.get('DRY_RUN', 'false').lower() == 'true'
    
    if not github_token:
        print("Error: One of the following environment variables is required:", file=sys.stderr)
        print("  - COPILOT_GITHUB_TOKEN", file=sys.stderr)
        print("  - GH_TOKEN", file=sys.stderr)
        print("  - GITHUB_TOKEN", file=sys.stderr)
        sys.exit(1)
    
    # Use custom prompt if provided, otherwise use default
    prompt = custom_prompt if custom_prompt else default_prompt
    
    if not prompt or prompt.strip() == "" or prompt == "No prompt file found":
        print("Error: No prompt provided (neither CUSTOM_PROMPT nor DEFAULT_PROMPT)", file=sys.stderr)
        print(f"  CUSTOM_PROMPT: {repr(custom_prompt)}", file=sys.stderr)
        print(f"  DEFAULT_PROMPT length: {len(default_prompt)}", file=sys.stderr)
        sys.exit(1)
    
    if debug:
        print(f"Content folder: {content_folder}")
        print(f"Prompt length: {len(prompt)} characters")
        print(f"Using custom prompt: {bool(custom_prompt)}")
        print(f"Dry run: {dry_run}")
    
    # Find all markdown files in the content folder
    content_path = Path(content_folder)
    if not content_path.exists():
        print(f"Error: Content folder {content_folder} does not exist", file=sys.stderr)
        sys.exit(1)
    
    # Find markdown files (excluding certain patterns)
    md_files = [
        f for f in content_path.rglob('*.md')
        if 'node_modules' not in str(f) and '.git' not in str(f)
    ]
    
    if debug:
        print(f"Found {len(md_files)} markdown files")
    
    if not md_files:
        print("No markdown files found to process")
        sys.exit(0)
    
    # Process each file
    changes_made = 0
    errors = 0
    for md_file in md_files:
        if debug:
            print(f"\nProcessing: {md_file}")
        
        try:
            if process_markdown_file(md_file, prompt, github_token, dry_run):
                changes_made += 1
        except Exception as e:
            errors += 1
            print(f"❌ Failed to process {md_file}: {e}", file=sys.stderr)
            if not debug:
                # In non-debug mode, continue processing other files
                continue
            else:
                # In debug mode, show full traceback
                import traceback
                traceback.print_exc()
    
    print(f"\n{'Would process' if dry_run else 'Processed'} {changes_made} file(s)")
    if errors > 0:
        print(f"⚠️  {errors} file(s) had errors during processing", file=sys.stderr)
    
    # Exit with error if there were processing errors
    if errors > 0:
        sys.exit(1)
    elif changes_made > 0 and not dry_run:
        sys.exit(0)
    elif changes_made == 0:
        print("No changes were made to any files")
        sys.exit(0)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
