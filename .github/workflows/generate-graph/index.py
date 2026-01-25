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
from typing import Set, Dict, Optional, Union
import time
import csv
import warnings

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
        debug: bool = False
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
        if self.debug:
            print(f"🌐 Starting crawl from: {self.start_url}")
            max_pages_str = str(self.max_pages) if self.max_pages is not None else "unlimited"
            print(f"   Max pages: {max_pages_str}, Max depth: {self.max_depth}")
        
        # Start with the initial URL
        self.queue.append((self.start_url, 0))
        
        while self.queue and (self.max_pages is None or len(self.visited) < self.max_pages):
            url, depth = self.queue.popleft()
            
            if depth > self.max_depth:
                continue
            
            if url in self.visited:
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
        """Save graph as a single CSV file with both nodes and edges.
        
        CSV includes all required fields:
        - Type: 'Node' or 'Edge'
        - Id: Node ID (for nodes only)
        - Label: Node label (for nodes only)
        - URL: Node URL (for nodes only)
        - Depth: Crawl depth (for nodes only)
        - Source: Source node URL (for edges only)
        - Target: Target node URL (for edges only)
        - EdgeType: Edge type, e.g., 'Directed' (for edges only)
        """
        try:
            # Generate base filename without extension
            base_name = os.path.splitext(base_path)[0]
            csv_path = f"{base_name}.csv"
            
            # Ensure all nodes have required attributes before exporting
            for node_id in self.graph.nodes():
                node_data = self.graph.nodes[node_id]
                if 'label' not in node_data:
                    node_data['label'] = node_data.get('url', str(node_id))
                if 'url' not in node_data:
                    node_data['url'] = node_data.get('label', str(node_id))
                if 'depth' not in node_data:
                    node_data['depth'] = 0
            
            # Create a single CSV file with both nodes and edges
            # Group edges immediately after their source nodes for better readability
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Write header with all required columns
                writer.writerow(['Type', 'Id', 'Label', 'URL', 'Depth', 'Source', 'Target', 'EdgeType'])
                
                # Build a map of source node to its outgoing edges
                edges_by_source = {}
                for source_id, target_id in self.graph.edges():
                    if source_id not in edges_by_source:
                        edges_by_source[source_id] = []
                    edges_by_source[source_id].append(target_id)
                
                # Write each node followed immediately by its outgoing edges
                for node_id in self.graph.nodes():
                    node_data = self.graph.nodes[node_id]
                    url = node_data.get('url', str(node_id))
                    label = node_data.get('label', url)
                    depth = node_data.get('depth', 0)
                    # For nodes: Type='Node', Id/Label/URL/Depth filled, Source/Target/EdgeType empty
                    # Use page title (label) as Id instead of numeric ID
                    writer.writerow(['Node', label, label, url, depth, '', '', ''])
                    
                    # Write all edges originating from this node immediately after the node
                    if node_id in edges_by_source:
                        for target_id in edges_by_source[node_id]:
                            target_node_data = self.graph.nodes[target_id]
                            target_url = target_node_data.get('url', str(target_id))
                            target_label = target_node_data.get('label', target_url)
                            # For edges: Type='Edge', Id/Label/Source/Target/EdgeType filled, URL/Depth empty
                            # Use target page title as Id and in Label field
                            writer.writerow(['Edge', target_label, target_label, '', '', url, target_url, 'Directed'])
            
            if self.debug:
                print(f"💾 Saved CSV file: {csv_path}")
                print(f"   Nodes: {self.graph.number_of_nodes()}")
                print(f"   Edges: {self.graph.number_of_edges()}")
        except Exception as e:
            print(f"❌ Error saving CSV file: {e}", file=sys.stderr)
            sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate a link graph from a website URL in CSV format.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python3 index.py --url https://example.com --output graph.csv

  # With custom limits
  python3 index.py --url https://example.com --output graph.csv --max-pages 200 --max-depth 3

  # Using environment variables (GitHub Actions style)
  export WEBSITE_URL='https://example.com'
  export OUTPUT_FILE='graph.csv'
  python3 index.py

Environment Variables:
  WEBSITE_URL    - Starting URL to crawl (required)
  OUTPUT_FILE    - Output CSV file path (default: graph.csv)
  MAX_PAGES      - Maximum pages to crawl (default: unlimited, set to number to limit)
  MAX_DEPTH      - Maximum crawl depth (default: 5)
  RESPECT_ROBOTS - Respect robots.txt (default: true)
  CRAWL_DELAY    - Delay between requests in seconds (default: 0.5)
  DEBUG          - Enable debug output (default: false)
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
        debug=debug
    )
    
    crawler.crawl()
    crawler.save_csv(output_file)
    
    print(f"✅ CSV file saved: {output_file}")
    print(f"   Nodes: {crawler.graph.number_of_nodes()}")
    print(f"   Edges: {crawler.graph.number_of_edges()}")


if __name__ == '__main__':
    main()
