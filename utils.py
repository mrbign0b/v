import json
import base64
from urllib.parse import urlparse, urlunparse, unquote, quote
import re
from collections import defaultdict

def create_sanitized_filename(url):
    """Creates a safe, valid filename from a URL."""
    sanitized = re.sub(r'https?://', '', url)
    sanitized = re.sub(r'[^\w\-_\.]', '_', sanitized)
    return f"{sanitized}.txt"

def get_link_fingerprint(uri):
    """Creates a simplified, unique identifier for a server configuration."""
    try:
        if uri.startswith("vmess://"):
            encoded_part = uri.split('://', 1)[1]
            padded_part = encoded_part + '=' * (-len(encoded_part) % 4)
            config_str = base64.b64decode(padded_part).decode('utf-8', errors='ignore')
            config = json.loads(config_str)
            return f"vmess_{config.get('add')}_{config.get('port')}_{config.get('id')}"
        else:
            parsed = urlparse(uri)
            return f"{parsed.scheme}_{parsed.username}@{parsed.hostname}:{parsed.port}"
    except Exception:
        return uri

def categorize_links(links):
    """Groups a list of V2Ray links into a dictionary by their protocol."""
    categorized = defaultdict(list)
    for link in links:
        try:
            protocol = urlparse(link).scheme
            if protocol:
                categorized[protocol].append(link)
        except (ValueError, IndexError):
            continue
    return categorized

def format_and_replace_remark(link, new_name, ping):
    """Updates the remark of a V2Ray link to a new name and appends the ping."""
    ping_str = f"| Ping: {ping}ms"
    try:
        if link.startswith("vmess://"):
            encoded_part = link.split('://', 1)[1]
            padded_part = encoded_part + '=' * (-len(encoded_part) % 4)
            config_str = base64.b64decode(padded_part).decode('utf-8', errors='ignore')
            config = json.loads(config_str)
            config['ps'] = f"{new_name} {ping_str}"
            new_json_str = json.dumps(config, separators=(',', ':'))
            new_encoded_part = base64.b64encode(new_json_str.encode('utf-8')).decode('utf-8').rstrip("=")
            return f"vmess://{new_encoded_part}"
        else:
            parsed = urlparse(link)
            new_fragment = f"{new_name} {ping_str}"
            new_parts = parsed._replace(fragment=quote(new_fragment))
            return urlunparse(new_parts)
    except Exception:
        return link

def save_links_to_file(links, filename):
    """Saves a list of links to a specified file."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('\n'.join(links))
        print(f"Successfully saved {len(links)} links to {filename}")
    except IOError as e:
        print(f"Error: Could not write to file {filename}. Reason: {e}")

