#!/usr/bin/env python3
"""
Generate a link graph from a website URL.

This script crawls a website starting from a given URL and builds a graph
of all internal links. The graph is saved in GEXF format for import into Gephi.

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
from typing import Set, Dict, Optional
import time

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
        max_pages: int = 100,
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
            print(f"   Max pages: {self.max_pages}, Max depth: {self.max_depth}")
        
        # Start with the initial URL
        self.queue.append((self.start_url, 0))
        
        while self.queue and len(self.visited) < self.max_pages:
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
            
            # Add node to graph
            self.graph.add_node(url, label=url, depth=depth)
            
            # Extract links
            links = self._extract_links(html, url)
            
            # Add edges and queue new URLs
            for link in links:
                self.graph.add_edge(url, link)
                
                if link not in self.visited and depth < self.max_depth:
                    self.queue.append((link, depth + 1))
            
            # Respect rate limiting
            if self.delay > 0:
                time.sleep(self.delay)
        
        if self.debug:
            print(f"\n✅ Crawl complete: {len(self.visited)} pages, {self.graph.number_of_edges()} links")
    
    def save_gexf(self, output_path: str):
        """Save graph in GEXF format for Gephi."""
        try:
            nx.write_gexf(self.graph, output_path)
            if self.debug:
                print(f"💾 Saved graph to: {output_path}")
                print(f"   Nodes: {self.graph.number_of_nodes()}")
                print(f"   Edges: {self.graph.number_of_edges()}")
        except Exception as e:
            print(f"❌ Error saving graph: {e}", file=sys.stderr)
            sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate a link graph from a website URL in GEXF format for Gephi.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python3 index.py --url https://example.com --output graph.gexf

  # With custom limits
  python3 index.py --url https://example.com --output graph.gexf --max-pages 200 --max-depth 3

  # Using environment variables (GitHub Actions style)
  export WEBSITE_URL='https://example.com'
  export OUTPUT_FILE='graph.gexf'
  python3 index.py

Environment Variables:
  WEBSITE_URL    - Starting URL to crawl (required)
  OUTPUT_FILE    - Output GEXF file path (default: graph.gexf)
  MAX_PAGES      - Maximum pages to crawl (default: 100)
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
        default='graph.gexf',
        help='Output GEXF file path (default: graph.gexf or OUTPUT_FILE env var)'
    )
    parser.add_argument(
        '--max-pages',
        type=int,
        default=100,
        help='Maximum pages to crawl (default: 100 or MAX_PAGES env var)'
    )
    parser.add_argument(
        '--max-depth',
        type=int,
        default=5,
        help='Maximum crawl depth (default: 5 or MAX_DEPTH env var)'
    )
    parser.add_argument(
        '--respect-robots',
        action='store_true',
        default=True,
        help='Respect robots.txt (default: true)'
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
        default=0.5,
        help='Delay between requests in seconds (default: 0.5 or CRAWL_DELAY env var)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug output (or use DEBUG=true env var)'
    )
    
    args = parser.parse_args()
    
    # Get values from command-line arguments or environment variables
    website_url = args.website_url or os.environ.get('WEBSITE_URL')
    output_file = args.output_file or os.environ.get('OUTPUT_FILE', 'graph.gexf')
    max_pages = args.max_pages or int(os.environ.get('MAX_PAGES', '100'))
    max_depth = args.max_depth or int(os.environ.get('MAX_DEPTH', '5'))
    respect_robots = args.respect_robots if args.website_url else (
        os.environ.get('RESPECT_ROBOTS', 'true').lower() == 'true'
    )
    delay = args.delay or float(os.environ.get('CRAWL_DELAY', '0.5'))
    debug = args.debug or os.environ.get('DEBUG', 'false').lower() == 'true'
    
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
    crawler.save_gexf(output_file)
    
    print(f"✅ Graph saved to: {output_file}")
    print(f"   Nodes: {crawler.graph.number_of_nodes()}")
    print(f"   Edges: {crawler.graph.number_of_edges()}")


if __name__ == '__main__':
    main()
