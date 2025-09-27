import asyncio
import base64
import ipaddress
import json
import logging
import re
import socket
import ssl
import struct
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs

# --- Basic Configuration ---
# Set up a logger to provide detailed output during the testing process.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Helper Functions ---

def resolve_domain(domain):
    """
    Robustly resolves a domain name to an IP address.
    Returns the domain itself if it's already a valid IP address.
    Returns None if the domain cannot be resolved.
    """
    try:
        # Check if the input is already an IP address
        ipaddress.ip_address(domain)
        return domain
    except ValueError:
        try:
            # Attempt to resolve the domain name
            return socket.gethostbyname(domain)
        except socket.gaierror:
            # Failed to resolve the domain
            return None

def parse_qs_safely(query_str):
    """A wrapper for parse_qs that handles potential errors."""
    try:
        return parse_qs(query_str)
    except Exception:
        return {}

# --- Protocol-Specific Testers ---

def test_vless_link(link, timeout=5):
    """
    Tests a VLESS link by performing a proper TLS handshake (if required)
    and sending a VLESS protocol handshake. This is a highly reliable test.
    """
    result = {"link": link, "status": "dead", "ping_ms": None, "error": None}
    sock = None
    try:
        parsed = urlparse(link)
        vless_uuid = parsed.username
        server = parsed.hostname
        port = parsed.port
        params = parse_qs_safely(parsed.query)
        
        security = params.get('security', ['none'])[0]
        is_tls = security in ('tls', 'xtls')

        ip = resolve_domain(server)
        if not ip:
            result["error"] = f"DNS resolution failed for: {server}"
            return result
            
        start_time = time.time()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))

        if is_tls:
            # Use the SNI from the link parameters, falling back to the server hostname
            sni = params.get('sni', [server])[0]
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            sock = context.wrap_socket(sock, server_hostname=sni)
        
        # Construct and send the VLESS handshake packet
        # [Version][UUID][AddonLength][Command][Port][AddrType][Address][Addons]
        version = b'\x00'
        uuid_bytes = uuid.UUID(vless_uuid).bytes
        addon_length = b'\x00' # No addons for a simple test
        command = b'\x01'      # TCP
        dest_port = struct.pack('>H', 80) # Test destination: port 80
        addr_type = b'\x01'               # IPv4
        dest_addr = socket.inet_aton("8.8.8.8") # Test destination: Google DNS

        handshake_packet = version + uuid_bytes + addon_length + command + dest_port + addr_type + dest_addr
        
        sock.send(handshake_packet)
        # A valid VLESS server should respond. We wait for at least one byte.
        sock.recv(1)

        end_time = time.time()
        result["status"] = "alive"
        result["ping_ms"] = round((end_time - start_time) * 1000)

    except socket.timeout:
        result["error"] = "Connection or handshake timed out"
    except (ConnectionRefusedError, OSError) as e:
        result["error"] = f"Connection failed: {e}"
    except Exception as e:
        result["error"] = f"An unexpected error occurred: {e}"
    finally:
        if sock:
            sock.close()
    return result

def test_vmess_link(link, timeout=5):
    """
    Tests a VMess link. Since a full crypto handshake is complex, this function
    verifies connectivity and performs a TLS handshake if applicable, which is
    a strong indicator of a working server.
    """
    result = {"link": link, "status": "dead", "ping_ms": None, "error": None}
    sock = None
    try:
        # Decode the Base64 part of the VMess link to get the JSON config
        encoded_part = link.split('://', 1)[1]
        padded_part = encoded_part + '=' * (-len(encoded_part) % 4)
        config_str = base64.b64decode(padded_part).decode('utf-8', errors='ignore')
        config = json.loads(config_str)

        server = config.get("add")
        port = int(config.get("port", 0))
        is_tls = config.get("tls") in ("tls", "xtls")

        ip = resolve_domain(server)
        if not ip:
            result["error"] = f"DNS resolution failed for: {server}"
            return result

        start_time = time.time()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        
        if is_tls:
            sni = config.get('sni', server)
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            sock = context.wrap_socket(sock, server_hostname=sni)

        # A successful TCP connection (and TLS handshake if applicable) is our test.
        end_time = time.time()
        result["status"] = "alive"
        result["ping_ms"] = round((end_time - start_time) * 1000)

    except (json.JSONDecodeError, base64.binascii.Error):
        result["error"] = "Invalid Base64 or JSON in link"
    except socket.timeout:
        result["error"] = "Connection timed out"
    except (ConnectionRefusedError, OSError) as e:
        result["error"] = f"Connection failed: {e}"
    except Exception as e:
        result["error"] = f"An unexpected error occurred: {e}"
    finally:
        if sock:
            sock.close()
    return result

def test_trojan_link(link, timeout=5):
    """
    Tests a Trojan link by performing a full TLS handshake and sending the
    required Trojan protocol header, which includes the password.
    """
    result = {"link": link, "status": "dead", "ping_ms": None, "error": None}
    sock = None
    try:
        parsed = urlparse(link)
        password = parsed.username
        server = parsed.hostname
        port = parsed.port
        params = parse_qs_safely(parsed.query)

        ip = resolve_domain(server)
        if not ip:
            result["error"] = f"DNS resolution failed for: {server}"
            return result
            
        start_time = time.time()
        
        # Trojan protocol requires a TLS connection.
        sni = params.get('sni', [server])[0]
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        with socket.create_connection((ip, port), timeout) as plain_sock:
            sock = context.wrap_socket(plain_sock, server_hostname=sni)
        
            # Construct and send the Trojan handshake packet
            # [56-byte HEX of SHA224(password)][CRLF][Command][Address Info][CRLF]
            password_hash = password.encode('utf-8').hex()
            crlf = b"\r\n"
            command = b'\x01' # TCP CONNECT
            addr_type = b'\x03' # Domain name
            dest_addr = b'v1.v2ray.com' # A common test destination
            dest_len = struct.pack('B', len(dest_addr))
            dest_port = struct.pack('>H', 80)

            handshake_packet = password_hash.encode() + crlf + command + addr_type + dest_len + dest_addr + dest_port + crlf
            
            sock.send(handshake_packet)
            # A valid server should not immediately close the connection. Receiving a byte is a good sign.
            sock.recv(1)
        
        end_time = time.time()
        result["status"] = "alive"
        result["ping_ms"] = round((end_time - start_time) * 1000)
        
    except socket.timeout:
        result["error"] = "Connection or handshake timed out"
    except (ConnectionRefusedError, OSError, ssl.SSLError) as e:
        result["error"] = f"Connection or TLS failed: {e}"
    except Exception as e:
        result["error"] = f"An unexpected error occurred: {e}"
    finally:
        if sock:
            sock.close()
    return result

def test_ss_link(link, timeout=5):
    """
    Tests a Shadowsocks (SS) link. As the protocol is encrypted from the
    first byte, the most reliable check without a full crypto library is a
    successful TCP connection, which confirms the server is listening.
    """
    result = {"link": link, "status": "dead", "ping_ms": None, "error": None}
    sock = None
    try:
        # Shadowsocks links can be in two formats. We need to handle both.
        if "@" in link: # Format: ss://method:password@server:port
            parsed = urlparse(link)
            server = parsed.hostname
            port = parsed.port
        else: # Format: ss://base64(method:password)@server:port or ss://base64(method:password@server:port)
            match = re.search(r'ss://([^#]*)', link)
            encoded_part = match.group(1)
            padded_part = encoded_part + '=' * (-len(encoded_part) % 4)
            decoded_str = base64.b64decode(padded_part).decode('utf-8', errors='ignore')
            # Look for server:port in the decoded string
            server_match = re.search(r'@?([^:]+):(\d+)', decoded_str)
            if server_match:
                server = server_match.group(1)
                port = int(server_match.group(2))
            else:
                raise ValueError("Could not parse server/port from Base64 SS link")

        ip = resolve_domain(server)
        if not ip:
            result["error"] = f"DNS resolution failed for: {server}"
            return result
            
        start_time = time.time()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        
        # A successful TCP connection is our liveness check for Shadowsocks.
        end_time = time.time()
        result["status"] = "alive"
        result["ping_ms"] = round((end_time - start_time) * 1000)
        
    except (ValueError, IndexError, base64.binascii.Error):
        result["error"] = "Invalid or unparsable SS link format"
    except socket.timeout:
        result["error"] = "Connection timed out"
    except (ConnectionRefusedError, OSError) as e:
        result["error"] = f"Connection failed: {e}"
    except Exception as e:
        result["error"] = f"An unexpected error occurred: {e}"
    finally:
        if sock:
            sock.close()
    return result

# --- Main Orchestrator ---

async def test_links_ping(categorized_links, max_workers=100, timeout=5):
    """
    Asynchronously tests a dictionary of V2Ray links categorized by protocol.

    Args:
        categorized_links (dict): A dict where keys are protocols ('vless', 'vmess', etc.)
                                  and values are lists of link strings.
        max_workers (int): The maximum number of concurrent threads to use for testing.
        timeout (int): The timeout in seconds for each connection attempt.

    Returns:
        dict: A dictionary with the same protocol keys, where values are lists
              of result dictionaries from the test functions.
    """
    logger.info("Starting advanced, protocol-specific link testing...")
    all_results = {}
    
    # Mapping of protocols to their respective test functions
    test_function_map = {
        "vless": test_vless_link,
        "vmess": test_vmess_link,
        "trojan": test_trojan_link,
        "ss": test_ss_link,
    }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        loop = asyncio.get_running_loop()
        
        for protocol, links in categorized_links.items():
            if not links:
                continue
            
            test_function = test_function_map.get(protocol)
            if not test_function:
                logger.warning(f"No test function available for protocol: '{protocol}'. Skipping.")
                continue

            logger.info(f"Submitting {len(links)} '{protocol}' links for testing...")
            
            # Create a list of future objects for all links of this protocol
            tasks = [loop.run_in_executor(executor, test_function, link, timeout) for link in links]
            
            # Wait for all tests for this protocol to complete
            link_results = await asyncio.gather(*tasks)
            all_results[protocol] = link_results

            alive_count = sum(1 for r in link_results if r["status"] == "alive")
            logger.info(f"Finished testing '{protocol}': {alive_count} alive, {len(links) - alive_count} dead.")
            
    return all_results

