"""
Terabox video downloader.

Flow:
1. Extract surl (share token) from the public URL.
2. Call the Terabox filelist API to get metadata + dlink.
3. Resolve the real download URL by following redirects (HEAD request).
4. Stream the file to disk.
"""

import re
import os
import uuid
import logging
import asyncio
import aiohttp
import aiofiles
from typing import Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/terabox_downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Headers that mimic a real browser — required by Terabox
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.terabox.com/",
    "Accept-Language": "en-US,en;q=0.9",
}

# Known Terabox API base — same across branded mirrors
API_BASE = "https://www.terabox.com"
FILELIST_API = f"{API_BASE}/api/shorturlinfo"
DOWNLOAD_API = f"{API_BASE}/api/download"


class TeraboxDownloader:

    def _extract_surl(self, url: str) -> Optional[str]:
        """Extract the share token (surl) from a Terabox URL."""
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)

        # ?surl=...
        if "surl" in qs:
            return qs["surl"][0]

        # /s/XXXXXX  or  /sharing/link?surl=...
        match = re.search(r"/s/([A-Za-z0-9_-]+)", parsed.path)
        if match:
            return match.group(1)

        # last path segment as fallback
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts:
            return path_parts[-1]

        return None

    async def get_info(self, share_url: str) -> Optional[dict]:
        """
        Fetch file metadata from the Terabox share.
        Returns a dict with keys: name, size, download_url, fs_id
        """
        surl = self._extract_surl(share_url)
        if not surl:
            logger.error("Could not extract surl from: %s", share_url)
            return None

        logger.info("Fetching info for surl=%s", surl)

        # First, try the public short-url info endpoint
        params = {"shorturl": surl, "root": "1"}

        try:
            async with aiohttp.ClientSession(headers=BROWSER_HEADERS) as session:
                async with session.get(
                    FILELIST_API, params=params, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    data = await resp.json(content_type=None)

            logger.debug("Filelist API response: %s", data)

            if data.get("errno") != 0:
                # Fallback: try alternative third-party resolver
                return await self._resolve_via_third_party(share_url)

            file_list = data.get("list", [])
            if not file_list:
                return None

            file = file_list[0]
            return {
                "name": file.get("server_filename", "video.mp4"),
                "size": file.get("size", 0),
                "fs_id": file.get("fs_id"),
                "download_url": file.get("dlink") or await self._get_dlink(file, surl, data),
            }

        except Exception as e:
            logger.exception("Error fetching info: %s", e)
            # Fallback
            return await self._resolve_via_third_party(share_url)

    async def _get_dlink(self, file: dict, surl: str, share_data: dict) -> Optional[str]:
        """Get a direct download link using the Terabox download API."""
        try:
            uk = share_data.get("uk") or share_data.get("share_uk")
            share_id = share_data.get("shareid")
            fs_id = file.get("fs_id")

            if not all([uk, share_id, fs_id]):
                return None

            params = {
                "uk": uk,
                "shareid": share_id,
                "fs_ids": f"[{fs_id}]",
                "sign": share_data.get("sign", ""),
                "timestamp": share_data.get("timestamp", ""),
            }

            async with aiohttp.ClientSession(headers=BROWSER_HEADERS) as session:
                async with session.get(
                    DOWNLOAD_API, params=params, timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    data = await resp.json(content_type=None)

            links = data.get("dlink", [])
            if links:
                return links[0].get("dlink")

        except Exception as e:
            logger.warning("Could not get dlink: %s", e)

        return None

    async def _resolve_via_third_party(self, share_url: str) -> Optional[dict]:
        """
        Fallback: use the public terabox-downloader API (api.teradownloader.com).
        This is a well-known public scraper API.
        """
        api_url = "https://teradownloader.com/api"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url,
                    params={"url": share_url},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    data = await resp.json(content_type=None)

            logger.debug("Third-party API response: %s", data)

            if not data.get("ok"):
                return None

            # Response varies; try common keys
            item = data.get("data") or data
            return {
                "name": item.get("file_name") or item.get("title", "video.mp4"),
                "size": int(item.get("size_bytes") or item.get("size") or 0),
                "download_url": item.get("download_link") or item.get("url"),
            }

        except Exception as e:
            logger.warning("Third-party resolver failed: %s", e)

        return None

    async def download(self, info: dict) -> Optional[str]:
        """
        Download the file to disk.
        Returns the local file path, or None on failure.
        """
        url = info.get("download_url")
        if not url:
            logger.error("No download URL in info dict")
            return None

        name = info.get("name", "video.mp4")
        # Sanitise filename
        name = re.sub(r'[\\/*?:"<>|]', "_", name)
        # Ensure unique filename
        unique_name = f"{uuid.uuid4().hex[:8]}_{name}"
        dest = os.path.join(DOWNLOAD_DIR, unique_name)

        logger.info("Downloading: %s → %s", url, dest)

        try:
            async with aiohttp.ClientSession(headers=BROWSER_HEADERS) as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=600), allow_redirects=True
                ) as resp:
                    if resp.status != 200:
                        logger.error("Download failed with HTTP %s", resp.status)
                        return None

                    async with aiofiles.open(dest, "wb") as f:
                        async for chunk in resp.content.iter_chunked(1024 * 512):  # 512 KB
                            await f.write(chunk)

            logger.info("Download complete: %s", dest)
            return dest

        except asyncio.TimeoutError:
            logger.error("Download timed out")
        except Exception as e:
            logger.exception("Download error: %s", e)

        return None
