import asyncio
import os
import aiohttp
import time
from collections import defaultdict

import config
from scrapers import (
    V2NodesScraper, V2NodesSubscriptionScraper, GitHubRawScraper,
    TelegramScraper, OpenProxyListScraper
)
from tester import test_links_ping
from utils import (
    get_link_fingerprint, categorize_links, format_and_replace_remark,
    save_links_to_file, create_sanitized_filename
)

# Define paths relative to the execution root in the GitHub Action runner
PRIVATE_REPO_PATH = 'private_repo'
PUBLIC_REPO_PATH = 'public_repo'

def calculate_score(server_data, source_weights, score_weights):
    """Calculates a score for a server based on its source and ping."""
    source = server_data.get('source', 'unknown')
    ping = server_data.get('ping', 9999)

    source_weight = source_weights.get(source, 1.0)
    ping_penalty = ping / 1000  # Normalize ping to a smaller number

    score = (source_weight * score_weights.get('source', 1.0)) + \
            (ping_penalty * score_weights.get('ping', -1.0))
    return score

async def main():
    # --- Setup ---
    storage_path = os.path.join(PRIVATE_REPO_PATH, config.SOURCE_STORAGE_DIR)
    os.makedirs(storage_path, exist_ok=True)
    
    all_found_links = {}

    # --- Initialize Scrapers ---
    scrapers = []
    scrapers.append(TelegramScraper(config.HIGH_PRIORITY_TELEGRAM_URLS))
    scrapers.append(TelegramScraper(config.STANDARD_SOURCES_CONFIG["telegram_urls"]))
    github_token = os.getenv('V2RAY_TOKEN')
    scrapers.append(GitHubRawScraper(
        public_urls=config.STANDARD_SOURCES_CONFIG["github_urls"],
        private_urls=config.PRIVATE_GITHUB_URLS, token=github_token
    ))
    available_scrapers = {
        "V2NodesScraper": V2NodesScraper, "V2NodesSubscriptionScraper": V2NodesSubscriptionScraper,
        "OpenProxyListScraper": OpenProxyListScraper
    }
    for name in config.STANDARD_SOURCES_CONFIG["other_scrapers"]:
        if name in available_scrapers:
            scrapers.append(available_scrapers[name]())

    # --- Scraping Cycles ---
    for i in range(config.SCRAPE_CYCLES):
        print(f"\n--- Starting Scraping Cycle {i + 1}/{config.SCRAPE_CYCLES} ---")
        async with aiohttp.ClientSession() as session:
            tasks = [scraper.run(session) for scraper in scrapers]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            cycle_links_found = 0
            for scraper_result in results:
                if isinstance(scraper_result, list):
                    for link, source_url in scraper_result:
                        fingerprint = get_link_fingerprint(link)
                        if fingerprint not in all_found_links:
                            all_found_links[fingerprint] = {"uri": link, "source": source_url}
                            cycle_links_found += 1
        print(f"Cycle {i + 1} complete. Found {cycle_links_found} new unique links.")
        if i < config.SCRAPE_CYCLES - 1:
            await asyncio.sleep(config.CYCLE_INTERVAL_SECONDS)

    # --- Load, Combine, and Cap ---
    master_links_to_test = set()
    links_by_source = defaultdict(list)
    # Use all freshly scraped links for the source mapping
    for data in all_found_links.values():
        links_by_source[data['source']].append(data['uri'])

    for source_url, new_links in links_by_source.items():
        filename = create_sanitized_filename(source_url)
        filepath = os.path.join(storage_path, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                existing_links = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            existing_links = []
        
        unique_links = list(dict.fromkeys(existing_links + new_links))
        capped_links = unique_links[-config.SOURCE_LINK_LIMIT:]
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(capped_links))
        
        master_links_to_test.update(capped_links)

    # --- Testing Phase ---
    print(f"\n--- Testing {len(master_links_to_test)} total unique links from history. ---")
    categorized = categorize_links(list(master_links_to_test))
    test_results = await test_links_ping(
        categorized, max_workers=config.TESTER_WORKER_COUNT, timeout=config.LINK_TEST_TIMEOUT
    )

    # --- Processing and Saving ---
    alive_servers = []
    
    # Re-create a source map from ALL historical and new links to ensure we can find the source for any alive link
    source_map = {}
    all_source_files = os.listdir(storage_path)
    for fname in all_source_files:
        # This is a bit simplistic, assumes filename maps back to a source URL
        # A more robust system might store source in a JSON object with the link
        try:
            with open(os.path.join(storage_path, fname), 'r') as f:
                for line in f:
                    link = line.strip()
                    if link:
                        fingerprint = get_link_fingerprint(link)
                        # This part is tricky, we need to map filename back to URL
                        # For now, let's rely on the fresh scrape map, it's more reliable
                        pass
        except Exception:
            continue

    # The source_map from the current run is the most accurate for attributing sources
    source_map_current_run = {get_link_fingerprint(data['uri']): data['source'] for data in all_found_links.values()}

    for protocol, results in test_results.items():
        for result in results:
            if result.get("status") == "alive":
                fingerprint = get_link_fingerprint(result["link"])
                # Prioritize source from current run, fallback to 'unknown_historical'
                source = source_map_current_run.get(fingerprint, "unknown_historical")
                server_data = {"uri": result["link"], "ping": result["ping_ms"], "source": source}
                # Calculate score for each alive server
                server_data['score'] = calculate_score(server_data, config.SOURCE_WEIGHTS, config.SCORE_WEIGHTS)
                alive_servers.append(server_data)
    
    print(f"\n--- Test complete. Found {len(alive_servers)} alive servers. Scoring and sorting... ---")
    
    # Separate servers into high-priority and standard lists
    high_priority_links = []
    standard_links = []
    for server in alive_servers:
        if server['source'] in config.HIGH_PRIORITY_TELEGRAM_URLS or server['source'] in config.PRIVATE_GITHUB_URLS:
            high_priority_links.append(server)
        else:
            standard_links.append(server)

    # Sort both lists by the calculated score in descending order (higher score is better)
    high_priority_links.sort(key=lambda x: x['score'], reverse=True)
    standard_links.sort(key=lambda x: x['score'], reverse=True)

    # Combine the lists, applying the limit to the standard list
    final_servers = high_priority_links + standard_links[:config.STANDARD_SOURCES_CONFIG['limit']]
    
    print(f"Total servers in final list: {len(final_servers)}")

    # Format the final links for saving
    final_formatted_links = [format_and_replace_remark(s['uri'], "@netiranfree", s['ping']) for s in final_servers]
    
    final_output_path = os.path.join(PRIVATE_REPO_PATH, "working_servers.txt")
    save_links_to_file(final_formatted_links, final_output_path)

if __name__ == "__main__":
    asyncio.run(main())

