import base64
import asyncio
import aiohttp
from bs4 import BeautifulSoup

# A base class for all scrapers to inherit from, promoting a consistent interface.
class Scraper:
    def __init__(self, name):
        self.name = name
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    async def run(self, session):
        """Each scraper must implement this method to perform its scraping task."""
        raise NotImplementedError

    def _extract_links_from_text(self, text, source_url):
        """
        A helper method to extract V2Ray links from a block of text and pair them 
        with their source URL. Returns a list of (link, source_url) tuples.
        """
        links = []
        for line in text.strip().splitlines():
            line = line.strip()
            if line.startswith(('vless://', 'vmess://', 'trojan://', 'ss://')):
                links.append((line, source_url))
        return links

# Scraper for V2Nodes.com individual server pages.
class V2NodesScraper(Scraper):
    def __init__(self):
        super().__init__("V2Nodes")
        self.base_url = "https://v2nodes.com/"

    async def run(self, session):
        server_links = await self._scrape_main_page(session)
        if not server_links:
            return []
        
        tasks = [self._scrape_server_page(session, link) for link in server_links]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten the list of lists into a single list
        all_links = [link for res in results if isinstance(res, list) for link in res]
        return all_links

    async def _scrape_main_page(self, session):
        try:
            async with session.get(self.base_url, headers=self.headers, timeout=15) as response:
                response.raise_for_status()
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                
                urls = []
                for a_tag in soup.select('#serversList a[href*="/servers/"]'):
                    urls.append(self.base_url.rstrip('/') + a_tag['href'])
                return urls
        except Exception as e:
            print(f"[{self.name}] Error on main page: {e}")
            return []

    async def _scrape_server_page(self, session, url):
        try:
            async with session.get(url, headers=self.headers, timeout=15) as response:
                response.raise_for_status()
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                textarea = soup.find('textarea')
                if textarea:
                    return self._extract_links_from_text(textarea.text, self.base_url)
                return []
        except Exception as e:
            # Don't print error for every single server page, as it's common for them to fail
            return []

# Scraper for V2Nodes subscription link.
class V2NodesSubscriptionScraper(Scraper):
    def __init__(self):
        super().__init__("V2NodesSubscription")
        self.base_url = "https://www.v2nodes.com/"

    async def run(self, session):
        subscription_url = await self._get_subscription_link(session)
        if not subscription_url:
            return []

        try:
            async with session.get(subscription_url, headers=self.headers, timeout=20) as response:
                response.raise_for_status()
                content = await response.text()
                decoded_string = base64.b64decode(content.strip()).decode('utf-8')
                return self._extract_links_from_text(decoded_string, subscription_url)
        except Exception as e:
            print(f"[{self.name}] Error fetching/decoding subscription: {e}")
            return []

    async def _get_subscription_link(self, session):
        try:
            async with session.get(self.base_url, headers=self.headers, timeout=15) as response:
                response.raise_for_status()
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                sub_input = soup.find('input', {'id': 'subscription'})
                return sub_input['value'] if sub_input else None
        except Exception:
            return None

# Scraper for raw text files from GitHub.
class GitHubRawScraper(Scraper):
    def __init__(self, public_urls, private_urls=None, token=None):
        super().__init__("GitHubRaw")
        self.urls = public_urls + (private_urls or [])
        if token and private_urls:
            self.headers['Authorization'] = f'token {token}'

    async def run(self, session):
        tasks = [self._fetch_raw_url(session, url) for url in self.urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [link for res in results if isinstance(res, list) for link in res]

    async def _fetch_raw_url(self, session, url):
        try:
            async with session.get(url, headers=self.headers, timeout=20) as response:
                response.raise_for_status()
                text = await response.text()
                return self._extract_links_from_text(text, url)
        except Exception as e:
            print(f"[{self.name}] Error fetching {url}: {e}")
            return []

# Scraper for Telegram channels.
class TelegramScraper(Scraper):
    def __init__(self, channel_urls):
        super().__init__("Telegram")
        self.channel_urls = channel_urls

    async def run(self, session):
        tasks = [self._scrape_channel(session, url) for url in self.channel_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [link for res in results if isinstance(res, list) for link in res]

    async def _scrape_channel(self, session, url):
        try:
            async with session.get(url, headers=self.headers, timeout=20) as response:
                response.raise_for_status()
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                
                links = []
                for container in soup.select('div.tgme_widget_message_text'):
                    # Look for links in <code> or <pre> tags first for precision
                    code_tags = container.select('pre, code')
                    text_to_parse = "\n".join(tag.get_text() for tag in code_tags) if code_tags else container.get_text()
                    links.extend(self._extract_links_from_text(text_to_parse, url))
                return links
        except Exception as e:
            print(f"[{self.name}] Error scraping {url}: {e}")
            return []

# Scraper for OpenProxyList.com.
class OpenProxyListScraper(Scraper):
    def __init__(self):
        super().__init__("OpenProxyList")
        self.base_url = "https://openproxylist.com/v2ray/"

    async def run(self, session):
        page_content = await self._scrape_main_page(session)
        if not page_content:
            return []

        soup = BeautifulSoup(page_content, 'html.parser')
        tasks = []
        for a_tag in soup.find_all('a', text={'Raw List', 'V2Ray Subscription'}):
            if a_tag.get('href'):
                tasks.append(self._fetch_content(session, a_tag['href']))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [link for res in results if isinstance(res, list) for link in res]

    async def _scrape_main_page(self, session):
        try:
            async with session.get(self.base_url, headers=self.headers, timeout=15) as response:
                response.raise_for_status()
                return await response.text()
        except Exception as e:
            print(f"[{self.name}] Error on main page: {e}")
            return None

    async def _fetch_content(self, session, url):
        try:
            async with session.get(url, headers=self.headers, timeout=20) as response:
                response.raise_for_status()
                text = await response.text()
                return self._extract_links_from_text(text, self.base_url)
        except Exception as e:
            print(f"[{self.name}] Error fetching content from {url}: {e}")
            return []

