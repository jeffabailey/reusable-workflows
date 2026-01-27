#!/usr/bin/env python3
"""
Generate a link graph from a website URL.

This script crawls a website starting from a given URL and builds a graph
of all internal links. The graph is saved in CSV format.

Requirements:
- Python 3.11+
- networkx, requests, beautifulsoup4, lxml
"""

import os
import sys
import argparse
import urllib.parse
from urllib.robotparser import RobotFileParser
from collections import deque
from typing import Set, Dict, Optional, Union, List
import time
import csv
import json
import warnings
import fnmatch

# Suppress urllib3 OpenSSL/LibreSSL compatibility warning
# This is a known issue when urllib3 v2 is used with LibreSSL instead of OpenSSL
# The warning doesn't affect functionality, just compatibility messaging
try:
    from urllib3.exceptions import NotOpenSSLWarning
    warnings.filterwarnings('ignore', category=NotOpenSSLWarning)
except ImportError:
    # Fallback if urllib3 structure changes
    warnings.filterwarnings('ignore', message='.*urllib3.*OpenSSL.*', category=UserWarning)

try:
    import requests
    from bs4 import BeautifulSoup
    import networkx as nx
except ImportError as e:
    print(f"Error: Missing required dependency: {e}", file=sys.stderr)
    print("Please install: pip install networkx requests beautifulsoup4 lxml", file=sys.stderr)
    sys.exit(1)


class WebsiteGraphCrawler:
    """Crawls a website and builds a graph of internal links."""
    
    def __init__(
        self,
        start_url: str,
        max_pages: Optional[int] = None,
        max_depth: int = 5,
        respect_robots: bool = True,
        delay: float = 0.5,
        timeout: int = 10,
        debug: bool = False,
        ignore_paths: Optional[List[str]] = None
    ):
        self.start_url = start_url
        self.parsed_start = urllib.parse.urlparse(start_url)
        self.base_domain = f"{self.parsed_start.scheme}://{self.parsed_start.netloc}"
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.respect_robots = respect_robots
        self.delay = delay
        self.timeout = timeout
        self.debug = debug
        self.ignore_paths = ignore_paths or []
        
        self.graph = nx.DiGraph()
        self.visited: Set[str] = set()
        self.queue = deque()
        self.robots_parser: Optional[RobotFileParser] = None
        self.url_to_id: Dict[str, int] = {}  # Map URLs to numeric IDs
        self.next_id = 0
        
        # Setup robots.txt parser
        if self.respect_robots:
            self._setup_robots_parser()
    
    def _setup_robots_parser(self):
        """Setup robots.txt parser for the domain."""
        try:
            robots_url = urllib.parse.urljoin(self.base_domain, '/robots.txt')
            self.robots_parser = RobotFileParser()
            self.robots_parser.set_url(robots_url)
            self.robots_parser.read()
            if self.debug:
                print(f"✅ Loaded robots.txt from {robots_url}")
        except Exception as e:
            if self.debug:
                print(f"⚠️  Could not load robots.txt: {e}")
            self.robots_parser = None
    
    def _get_node_id(self, url: str) -> int:
        """Get or create a numeric ID for a URL."""
        if url not in self.url_to_id:
            self.url_to_id[url] = self.next_id
            self.next_id += 1
        return self.url_to_id[url]
    
    def _can_fetch(self, url: str) -> bool:
        """Check if URL can be fetched according to robots.txt."""
        if not self.robots_parser:
            return True
        try:
            return self.robots_parser.can_fetch('*', url)
        except Exception:
            return True
    
    def _should_ignore_url(self, url: str) -> bool:
        """Check if URL should be ignored based on ignore_paths patterns."""
        if not self.ignore_paths:
            return False
        
        # Debug: Print ignore_paths if debug is enabled
        if self.debug and len(self.ignore_paths) > 0:
            # Only print once to avoid spam
            if not hasattr(self, '_ignore_paths_printed'):
                print(f"🔍 Checking ignore patterns: {self.ignore_paths}")
                self._ignore_paths_printed = True
        
        try:
            parsed = urllib.parse.urlparse(url)
            path = parsed.path
            
            # Ensure path starts with / for consistent matching
            if not path.startswith('/'):
                path = '/' + path
            
            # Normalize path for comparison (remove trailing slash except root)
            # This allows matching /categories with /categories/
            path_normalized = path.rstrip('/') if path != '/' else path
            
            # Check each ignore pattern
            for pattern in self.ignore_paths:
                pattern_original = pattern
                pattern = pattern.strip()
                if not pattern:
                    continue
                
                # Ensure pattern starts with / for consistent matching
                if not pattern.startswith('/'):
                    pattern = '/' + pattern
                
                # Handle patterns ending with * (prefix match)
                if pattern.endswith('*'):
                    # Remove the * and normalize
                    prefix = pattern.rstrip('*').rstrip('/')
                    # Match if normalized path equals prefix or starts with prefix/
                    # This matches /categories, /categories/, /categories/anything
                    if path_normalized == prefix or path_normalized.startswith(prefix + '/'):
                        if self.debug:
                            print(f"🚫 Ignoring URL (matches pattern '{pattern_original}'): {url}")
                        return True
                
                # Use fnmatch for wildcard matching (handles other wildcard patterns)
                pattern_normalized = pattern.rstrip('/') if pattern != '/' else pattern
                if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path_normalized, pattern):
                    if self.debug:
                        print(f"🚫 Ignoring URL (matches pattern '{pattern}'): {url}")
                    return True
                
                # Check exact match (normalized)
                if path_normalized == pattern_normalized or path == pattern:
                    if self.debug:
                        print(f"🚫 Ignoring URL (matches pattern '{pattern}'): {url}")
                    return True
            
            return False
        except Exception as e:
            if self.debug:
                print(f"⚠️  Error checking ignore pattern: {e}")
            return False
    
    def _normalize_url(self, url: str, base_url: str) -> Optional[str]:
        """Normalize and validate URL."""
        try:
            # Resolve relative URLs
            parsed = urllib.parse.urlparse(urllib.parse.urljoin(base_url, url))
            
            # Remove fragment
            normalized = urllib.parse.urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                ''  # Remove fragment
            ))
            
            # Only include URLs from the same domain
            if parsed.netloc != self.parsed_start.netloc:
                return None
            
            # Check if URL should be ignored
            if self._should_ignore_url(normalized):
                return None
            
            # Remove trailing slash for consistency (except root)
            if normalized.endswith('/') and normalized != self.base_domain + '/':
                normalized = normalized.rstrip('/')
            
            return normalized
        except Exception:
            return None
    
    def _extract_title(self, html: str) -> Optional[str]:
        """Extract page title from HTML."""
        try:
            soup = BeautifulSoup(html, 'lxml')
            title_tag = soup.find('title')
            if title_tag and title_tag.string:
                # Clean up the title: strip whitespace and limit length
                title = title_tag.string.strip()
                # Remove extra whitespace and newlines
                title = ' '.join(title.split())
                return title if title else None
        except Exception as e:
            if self.debug:
                print(f"⚠️  Error extracting title: {e}")
        return None
    
    def _extract_links(self, html: str, base_url: str) -> Set[str]:
        """Extract all internal links from HTML."""
        links = set()
        
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Find all <a> tags with href attributes
            for tag in soup.find_all('a', href=True):
                # Skip links that are inside a footer with class "post-footer"
                footer_parent = tag.find_parent('footer')
                if footer_parent and 'post-footer' in footer_parent.get('class', []):
                    if self.debug:
                        print(f"🚫 Skipping link in post-footer: {tag.get('href', '')}")
                    continue
                
                href = tag['href']
                normalized = self._normalize_url(href, base_url)
                
                if normalized and normalized not in self.visited:
                    links.add(normalized)
        
        except Exception as e:
            if self.debug:
                print(f"⚠️  Error parsing HTML from {base_url}: {e}")
        
        return links
    
    def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch a page and return its HTML content."""
        if not self._can_fetch(url):
            if self.debug:
                print(f"🚫 Blocked by robots.txt: {url}")
            return None
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; WebsiteGraphCrawler/1.0)'
            }
            response = requests.get(url, headers=headers, timeout=self.timeout, allow_redirects=True)
            response.raise_for_status()
            
            # Only process HTML content
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' not in content_type:
                if self.debug:
                    print(f"⚠️  Skipping non-HTML content: {url} ({content_type})")
                return None
            
            return response.text
        
        except requests.exceptions.RequestException as e:
            if self.debug:
                print(f"⚠️  Error fetching {url}: {e}")
            return None
    
    def crawl(self):
        """Crawl the website and build the graph."""
        print(f"🌐 Starting crawl from: {self.start_url}")
        max_pages_str = str(self.max_pages) if self.max_pages is not None else "unlimited"
        print(f"   Max pages: {max_pages_str}, Max depth: {self.max_depth}")
        
        # Always report ignore paths if configured
        if self.ignore_paths:
            print(f"🚫 Ignore paths configured ({len(self.ignore_paths)} pattern(s)):")
            for pattern in self.ignore_paths:
                print(f"   - {pattern}")
        else:
            print("🚫 No ignore paths configured")
        
        # Start with the initial URL
        self.queue.append((self.start_url, 0))
        
        while self.queue and (self.max_pages is None or len(self.visited) < self.max_pages):
            url, depth = self.queue.popleft()
            
            if depth > self.max_depth:
                continue
            
            if url in self.visited:
                continue
            
            # Check if URL should be ignored before processing
            if self._should_ignore_url(url):
                if self.debug:
                    print(f"🚫 Skipping ignored URL: {url}")
                # Still mark as visited to avoid reprocessing
                self.visited.add(url)
                continue
            
            self.visited.add(url)
            
            if self.debug:
                print(f"📄 [{len(self.visited)}/{self.max_pages}] Fetching: {url} (depth: {depth})")
            
            # Fetch the page
            html = self._fetch_page(url)
            if not html:
                continue
            
            # Get numeric ID for this URL
            node_id = self._get_node_id(url)
            
            # Extract page title
            title = self._extract_title(html)
            # Use title as label, fallback to URL if no title found
            label = title if title else url
            
            # Add node to graph with numeric ID, title as label, URL, and depth
            self.graph.add_node(node_id, label=label, url=url, depth=depth, title=title if title else None)
            
            # Extract links
            links = self._extract_links(html, url)
            
            # Add edges and queue new URLs
            for link in links:
                # Double-check that link is not ignored (should already be filtered by _normalize_url, but be safe)
                if self._should_ignore_url(link):
                    if self.debug:
                        print(f"🚫 Skipping ignored link: {link}")
                    continue
                
                target_id = self._get_node_id(link)
                # Ensure target node exists (it might not have been visited yet)
                # Use URL as label for unvisited nodes (title will be set when visited)
                if target_id not in self.graph:
                    self.graph.add_node(target_id, label=link, url=link)
                self.graph.add_edge(node_id, target_id)
                
                if link not in self.visited and depth < self.max_depth:
                    self.queue.append((link, depth + 1))
            
            # Respect rate limiting
            if self.delay > 0:
                time.sleep(self.delay)
        
        if self.debug:
            print(f"\n✅ Crawl complete: {len(self.visited)} pages, {self.graph.number_of_edges()} links")
    
    def save_csv(self, base_path: str):
        """Save graph as separate node and edge CSV files for Cytoscape.
        
        Creates two files:
        - nodes.csv: id, label, url, depth
        - edges.csv: source, target, interaction
        
        Cytoscape expects:
        - Edge file with source/target columns (required)
        - Optional node file with node attributes
        - IDs must match exactly between files
        """
        try:
            # Generate base filename without extension
            base_name = os.path.splitext(base_path)[0]
            nodes_path = f"{base_name}_nodes.csv"
            edges_path = f"{base_name}_edges.csv"
            
            # Ensure all nodes have required attributes before exporting
            for node_id in self.graph.nodes():
                node_data = self.graph.nodes[node_id]
                # Get URL first, with proper fallback
                url = node_data.get('url')
                if not url:  # Handle None, empty string, etc.
                    # Try to get URL from the reverse mapping (node_id -> URL)
                    url = next((u for u, nid in self.url_to_id.items() if nid == node_id), None)
                    if not url:
                        url = node_data.get('label', str(node_id))
                node_data['url'] = url
                
                if 'label' not in node_data or not node_data['label']:
                    node_data['label'] = url
                if 'depth' not in node_data:
                    node_data['depth'] = 0
            
            # Write nodes CSV file
            with open(nodes_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Write header: id, label, url, depth
                writer.writerow(['id', 'label', 'url', 'depth'])
                
                # Write each node
                for node_id in self.graph.nodes():
                    node_data = self.graph.nodes[node_id]
                    # Get URL, ensuring it's never None or empty
                    url = node_data.get('url')
                    if not url:  # Handle None, empty string, etc.
                        # Try to get URL from the reverse mapping (node_id -> URL)
                        url = next((u for u, nid in self.url_to_id.items() if nid == node_id), None)
                        if not url:
                            url = node_data.get('label', str(node_id))
                    # Ensure URL is a string
                    url = str(url) if url else str(node_id)
                    
                    label = node_data.get('label', url)
                    depth = node_data.get('depth', 0)
                    # Use URL as id (unique identifier for Cytoscape)
                    writer.writerow([url, label, url, depth])
            
            # Write edges CSV file
            with open(edges_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Write header: source, target, interaction
                writer.writerow(['source', 'target', 'interaction'])
                
                # Write each edge
                for source_id, target_id in self.graph.edges():
                    source_node_data = self.graph.nodes[source_id]
                    target_node_data = self.graph.nodes[target_id]
                    
                    # Get source URL, ensuring it's never None or empty
                    source_url = source_node_data.get('url')
                    if not source_url:  # Handle None, empty string, etc.
                        source_url = next((u for u, nid in self.url_to_id.items() if nid == source_id), None)
                        if not source_url:
                            source_url = source_node_data.get('label', str(source_id))
                    source_url = str(source_url) if source_url else str(source_id)
                    
                    # Get target URL, ensuring it's never None or empty
                    target_url = target_node_data.get('url')
                    if not target_url:  # Handle None, empty string, etc.
                        target_url = next((u for u, nid in self.url_to_id.items() if nid == target_id), None)
                        if not target_url:
                            target_url = target_node_data.get('label', str(target_id))
                    target_url = str(target_url) if target_url else str(target_id)
                    
                    # Write edge: source URL, target URL, interaction type
                    writer.writerow([source_url, target_url, 'Directed'])
            
            if self.debug:
                print(f"💾 Saved CSV files:")
                print(f"   Nodes: {nodes_path} ({self.graph.number_of_nodes()} nodes)")
                print(f"   Edges: {edges_path} ({self.graph.number_of_edges()} edges)")
            else:
                print(f"💾 Saved CSV files: {nodes_path}, {edges_path}")
        except Exception as e:
            print(f"❌ Error saving CSV file: {e}", file=sys.stderr)
            sys.exit(1)
    
    def save_json(self, output_path: str):
        """Save graph in Cytoscape.js JSON format.
        
        Format:
        {
          "elements": {
            "nodes": [
              {"data": {"id": "...", "label": "...", "url": "...", "depth": ...}}
            ],
            "edges": [
              {"data": {"source": "...", "target": "...", "interaction": "Directed"}}
            ]
          }
        }
        """
        try:
            # Ensure all nodes have required attributes before exporting
            for node_id in self.graph.nodes():
                node_data = self.graph.nodes[node_id]
                # Get URL first, with proper fallback
                url = node_data.get('url')
                if not url:  # Handle None, empty string, etc.
                    # Try to get URL from the reverse mapping (node_id -> URL)
                    url = next((u for u, nid in self.url_to_id.items() if nid == node_id), None)
                    if not url:
                        url = node_data.get('label', str(node_id))
                node_data['url'] = url
                
                if 'label' not in node_data or not node_data['label']:
                    node_data['label'] = url
                if 'depth' not in node_data:
                    node_data['depth'] = 0
            
            # Build nodes array
            nodes_array = []
            for node_id in self.graph.nodes():
                node_data = self.graph.nodes[node_id]
                # Get URL, ensuring it's never None or empty
                url = node_data.get('url')
                if not url:  # Handle None, empty string, etc.
                    url = next((u for u, nid in self.url_to_id.items() if nid == node_id), None)
                    if not url:
                        url = node_data.get('label', str(node_id))
                url = str(url) if url else str(node_id)
                
                label = node_data.get('label', url)
                depth = node_data.get('depth', 0)
                title = node_data.get('title')
                
                node_element = {
                    "data": {
                        "id": url,
                        "label": label,
                        "url": url,
                        "depth": depth
                    }
                }
                if title:
                    node_element["data"]["title"] = title
                
                nodes_array.append(node_element)
            
            # Build edges array
            edges_array = []
            for source_id, target_id in self.graph.edges():
                source_node_data = self.graph.nodes[source_id]
                target_node_data = self.graph.nodes[target_id]
                
                # Get source URL, ensuring it's never None or empty
                source_url = source_node_data.get('url')
                if not source_url:  # Handle None, empty string, etc.
                    source_url = next((u for u, nid in self.url_to_id.items() if nid == source_id), None)
                    if not source_url:
                        source_url = source_node_data.get('label', str(source_id))
                source_url = str(source_url) if source_url else str(source_id)
                
                # Get target URL, ensuring it's never None or empty
                target_url = target_node_data.get('url')
                if not target_url:  # Handle None, empty string, etc.
                    target_url = next((u for u, nid in self.url_to_id.items() if nid == target_id), None)
                    if not target_url:
                        target_url = target_node_data.get('label', str(target_id))
                target_url = str(target_url) if target_url else str(target_id)
                
                edges_array.append({
                    "data": {
                        "source": source_url,
                        "target": target_url,
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
            
            if self.debug:
                print(f"💾 Saved Cytoscape JSON:")
                print(f"   File: {output_path}")
                print(f"   Nodes: {len(nodes_array)}, Edges: {len(edges_array)}")
            else:
                print(f"💾 Saved Cytoscape JSON: {output_path}")
        
        except Exception as e:
            print(f"❌ Error saving JSON file: {e}", file=sys.stderr)
            sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate a link graph from a website URL in Cytoscape-compatible CSV format.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (creates graph_nodes.csv and graph_edges.csv)
  python3 index.py --url https://example.com --output graph.csv

  # With custom limits
  python3 index.py --url https://example.com --output graph.csv --max-pages 200 --max-depth 3

  # Using environment variables (GitHub Actions style)
  export WEBSITE_URL='https://example.com'
  export OUTPUT_FILE='graph.csv'
  python3 index.py

Output Files:
  The script creates CSV and JSON files for Cytoscape:
  - <output>_nodes.csv: Node attributes (id, label, url, depth)
  - <output>_edges.csv: Edge list (source, target, interaction)
  - <output>.json: Cytoscape.js JSON format (compatible with both desktop and JS library)
  
  Import nodes first, then edges in Cytoscape desktop, or use JSON for Cytoscape.js.

Environment Variables:
  WEBSITE_URL    - Starting URL to crawl (required)
  OUTPUT_FILE    - Base name for output CSV files (default: graph.csv)
  MAX_PAGES      - Maximum pages to crawl (default: unlimited, set to number to limit)
  MAX_DEPTH      - Maximum crawl depth (default: 5)
  RESPECT_ROBOTS - Respect robots.txt (default: true)
  CRAWL_DELAY    - Delay between requests in seconds (default: 0.5)
  DEBUG          - Enable debug output (default: false)
  IGNORE_PATHS   - URL paths to ignore, one per line (supports wildcards, default: empty)
        """
    )
    
    parser.add_argument(
        '--url',
        dest='website_url',
        help='Starting URL to crawl (or use WEBSITE_URL env var)'
    )
    parser.add_argument(
        '--output',
        dest='output_file',
        default=None,
        help='Output CSV file path (default: graph.csv or OUTPUT_FILE env var)'
    )
    parser.add_argument(
        '--max-pages',
        type=int,
        default=None,
        help='Maximum pages to crawl (default: unlimited, or MAX_PAGES env var)'
    )
    parser.add_argument(
        '--max-depth',
        type=int,
        default=None,
        help='Maximum crawl depth (default: 5 or MAX_DEPTH env var)'
    )
    parser.add_argument(
        '--respect-robots',
        dest='respect_robots',
        action='store_true',
        default=None,
        help='Respect robots.txt (default: true or RESPECT_ROBOTS env var)'
    )
    parser.add_argument(
        '--no-respect-robots',
        dest='respect_robots',
        action='store_false',
        help='Do not respect robots.txt'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=None,
        help='Delay between requests in seconds (default: 0.5 or CRAWL_DELAY env var)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug output (or use DEBUG=true env var)'
    )
    parser.add_argument(
        '--ignore-paths',
        dest='ignore_paths',
        type=str,
        default=None,
        help='URL paths to ignore, one per line (supports wildcards, or use IGNORE_PATHS env var)'
    )
    
    args = parser.parse_args()
    
    # Get values from command-line arguments or environment variables
    # Command-line arguments take precedence over environment variables
    website_url = args.website_url or os.environ.get('WEBSITE_URL')
    output_file = args.output_file if args.output_file is not None else os.environ.get('OUTPUT_FILE', 'graph.csv')
    max_pages_env = os.environ.get('MAX_PAGES')
    max_pages = args.max_pages if args.max_pages is not None else (int(max_pages_env) if max_pages_env else None)
    max_depth = args.max_depth if args.max_depth is not None else int(os.environ.get('MAX_DEPTH', '5'))
    respect_robots = args.respect_robots if args.respect_robots is not None else (
        os.environ.get('RESPECT_ROBOTS', 'true').lower() == 'true'
    )
    delay = args.delay if args.delay is not None else float(os.environ.get('CRAWL_DELAY', '0.5'))
    debug = args.debug if args.debug else (os.environ.get('DEBUG', 'false').lower() == 'true')
    
    # Parse ignore paths from argument or environment variable
    ignore_paths_str = args.ignore_paths or os.environ.get('IGNORE_PATHS', '')
    if ignore_paths_str:
        # Handle both literal \n sequences (from shell environment variables) and actual newlines
        # Replace literal \n with actual newlines, then split
        ignore_paths_str = ignore_paths_str.replace('\\n', '\n')
        ignore_paths = [line.strip() for line in ignore_paths_str.split('\n') if line.strip()]
    else:
        ignore_paths = []
    
    if not website_url:
        print("Error: WEBSITE_URL is required", file=sys.stderr)
        print("  Provide via --url argument or WEBSITE_URL environment variable", file=sys.stderr)
        sys.exit(1)
    
    # Validate URL
    try:
        parsed = urllib.parse.urlparse(website_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL")
    except Exception:
        print(f"Error: Invalid URL: {website_url}", file=sys.stderr)
        sys.exit(1)
    
    # Create crawler and run
    crawler = WebsiteGraphCrawler(
        start_url=website_url,
        max_pages=max_pages,
        max_depth=max_depth,
        respect_robots=respect_robots,
        delay=delay,
        debug=debug,
        ignore_paths=ignore_paths
    )
    
    crawler.crawl()
    crawler.save_csv(output_file)
    
    # Generate JSON file
    base_name = os.path.splitext(output_file)[0]
    json_file = f"{base_name}.json"
    crawler.save_json(json_file)
    
    # Generate filenames for the output message
    nodes_file = f"{base_name}_nodes.csv"
    edges_file = f"{base_name}_edges.csv"
    
    print(f"✅ Files saved:")
    print(f"   CSV Nodes: {nodes_file} ({crawler.graph.number_of_nodes()} nodes)")
    print(f"   CSV Edges: {edges_file} ({crawler.graph.number_of_edges()} edges)")
    print(f"   JSON: {json_file} (Cytoscape.js format)")
    print(f"   Import nodes first, then edges in Cytoscape (or use JSON for Cytoscape.js)")


if __name__ == '__main__':
    main()
