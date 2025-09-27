

# config.py

# --- Main Control ---
SCRAPE_CYCLES = 4
CYCLE_INTERVAL_SECONDS = 75

# --- Worker & Testing Configuration ---
TESTER_WORKER_COUNT = 200
LINK_TEST_TIMEOUT = 8

# --- State Management Configuration ---
SOURCE_STORAGE_DIR = "source_links"
SOURCE_LINK_LIMIT = 1000

# --- Scoring and Ranking Weights ---
# Assign a weight to each source. Higher weight means links from this source are preferred.
SOURCE_WEIGHTS = {
    "https://t.me/s/v2ray_configs_pool": 2.5,
    "https://t.me/s/ConfigsHub": 2.6,
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/main/v2ray_configs.txt": 1.2,
            "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt":1.4,
      "https://raw.githubusercontent.com/STR97/STRUGOV/refs/heads/main/STR.BYPASS#STR.BYPASS%F0%9F%91%BE":2,
      "https://raw.githubusercontent.com/VpnforWindowsSub/configs/master/Eternity":2
    # Give private sources a very high weight if you trust them
    # "https://raw.githubusercontent.com/your-user/your-private-repo/main/links.txt": 10.0,
}

# How much each factor contributes to the final score.
# 'source' is multiplied by the source's weight.
# 'ping' is a penalty; a higher ping results in a lower score.
SCORE_WEIGHTS = {
    "source": 2.0,
    "ping": -0.5,
}


# --- Source Configuration ---
HIGH_PRIORITY_TELEGRAM_URLS = [
    "https://t.me/s/v2ray_configs_pool",
    "https://t.me/s/ConfigsHubPlus",
    "https://t.me/s/ConfigsHub"
]
STANDARD_SOURCES_CONFIG = {
    "telegram_urls": [
        "https://t.me/s/DirectVPN", "https://t.me/s/FreeV2rays", "https://t.me/s/v2ray_outlineir",
        "https://t.me/s/VlessConfig", "https://t.me/s/ConfigsHUB", "https://t.me/s/PrivateVPNs",    "https://t.me/s/v2ray_configs_pool",
    "https://t.me/s/ConfigsHubPlus",
    "https://t.me/s/ConfigsHub",
        "https://t.me/s/ConfigsHUB2"
    ],
    "github_urls": [
       "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/main/v2ray_configs.txt",
        "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt",
      "https://raw.githubusercontent.com/STR97/STRUGOV/refs/heads/main/STR.BYPASS#STR.BYPASS%F0%9F%91%BE",
      "https://raw.githubusercontent.com/VpnforWindowsSub/configs/master/Eternity"
      
    ],
    "other_scrapers": ["V2NodesScraper", "V2NodesSubscriptionScraper", "OpenProxyListScraper"],
    # This limit is applied AFTER scoring and sorting.
    "limit": 5000
}
PRIVATE_GITHUB_URLS = []


