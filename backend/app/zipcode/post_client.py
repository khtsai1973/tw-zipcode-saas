"""中華郵政 3+3 Web Service 用戶端（GetZipAddress / GetZipCode）。"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

ENDPOINT = os.getenv("POST_WS_URL", "https://33wsp.post.gov.tw/LZWZIP/TZIP33.asmx")
ENABLED = os.getenv("POST_WS_ENABLED", "1") != "0"
TIMEOUT = float(os.getenv("POST_WS_TIMEOUT", "8"))

CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "ws_cache.sqlite3"

NS = {
    "soap": "http://schemas.xmlsoap.org/soap/envelope/",
    "tns": "http://tempuri.org/",
}


@dataclass
class PostLookup:
    zipcode: str | None
    normalized: str | None
    raw: str
    source: str = "post_ws"
    ok: bool = False
    message: str = ""


def _ensure_cache() -> sqlite3.Connection:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS zip_cache (
            addr_key TEXT PRIMARY KEY,
            zipcode TEXT,
            normalized TEXT,
            payload TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


def _cache_get(addr_key: str) -> PostLookup | None:
    conn = _ensure_cache()
    try:
        row = conn.execute(
            "SELECT zipcode, normalized, payload FROM zip_cache WHERE addr_key = ?",
            (addr_key,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    zipcode, normalized, payload = row
    return PostLookup(
        zipcode=zipcode or None,
        normalized=normalized or None,
        raw=payload or "",
        source="cache",
        ok=bool(zipcode and re.fullmatch(r"\d{6}", zipcode or "")),
        message="快取命中",
    )


def _cache_set(addr_key: str, result: PostLookup) -> None:
    conn = _ensure_cache()
    try:
        conn.execute(
            """
            INSERT INTO zip_cache(addr_key, zipcode, normalized, payload)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(addr_key) DO UPDATE SET
              zipcode=excluded.zipcode,
              normalized=excluded.normalized,
              payload=excluded.payload,
              updated_at=CURRENT_TIMESTAMP
            """,
            (addr_key, result.zipcode, result.normalized, result.raw),
        )
        conn.commit()
    finally:
        conn.close()


def _soap_request(action: str, body_inner: str) -> str:
    import ssl

    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        f"<soap:Body>{body_inner}</soap:Body>"
        "</soap:Envelope>"
    )
    data = envelope.encode("utf-8")
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f"http://tempuri.org/{action}",
    }

    # 先用系統憑證；若遇中華郵政憑證鏈問題再退回不驗證（僅此官方端點）
    contexts: list[ssl.SSLContext | None] = [ssl.create_default_context(), None]
    try:
        unverified = ssl._create_unverified_context()
        contexts.append(unverified)
    except Exception:  # noqa: BLE001
        pass

    last_err: Exception | None = None
    for ctx in contexts:
        try:
            req = urllib.request.Request(ENDPOINT, data=data, method="POST", headers=headers)
            if ctx is None:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    raise RuntimeError(f"郵政 WS 連線失敗：{last_err}")


def _xml_text(root: ET.Element, path: str) -> str | None:
    node = root.find(path, NS)
    if node is None:
        # 某些回應不帶 namespace
        local = path.split("}")[-1].split(":")[-1]
        for el in root.iter():
            if el.tag.endswith(local) and el.text:
                return el.text.strip()
        return None
    return (node.text or "").strip() or None


def get_zip_address(addr_str: str) -> PostLookup:
    """呼叫 GetZipAddress，回傳 JSON: {Address, ZipCode}。"""
    if not ENABLED:
        return PostLookup(None, None, "", message="郵政 WS 已停用", ok=False)

    key = addr_str.strip()
    cached = _cache_get(key)
    if cached and cached.ok:
        return cached

    body = f'<GetZipAddress xmlns="http://tempuri.org/"><addrStr>{_xml_escape(key)}</addrStr></GetZipAddress>'
    try:
        xml = _soap_request("GetZipAddress", body)
        root = ET.fromstring(xml)
        result_text = _xml_text(root, ".//tns:GetZipAddressResult") or _xml_text(
            root, ".//{http://tempuri.org/}GetZipAddressResult"
        )
        if not result_text:
            # 再嘗試任意 GetZipAddressResult
            for el in root.iter():
                if el.tag.endswith("GetZipAddressResult") and el.text:
                    result_text = el.text.strip()
                    break
        zipcode = None
        normalized = None
        if result_text:
            try:
                data = json.loads(result_text)
                zipcode = str(data.get("ZipCode") or data.get("zipcode") or "").strip() or None
                normalized = str(data.get("Address") or data.get("address") or "").strip() or None
            except json.JSONDecodeError:
                # 有時直接回六碼
                if re.fullmatch(r"\d{6}", result_text):
                    zipcode = result_text
        ok = bool(zipcode and re.fullmatch(r"\d{6}", zipcode))
        out = PostLookup(
            zipcode=zipcode,
            normalized=normalized,
            raw=result_text or xml[:500],
            source="post_ws",
            ok=ok,
            message="中華郵政 GetZipAddress" if ok else "郵政服務無有效郵遞區號",
        )
        if ok:
            _cache_set(key, out)
        return out
    except urllib.error.HTTPError as exc:
        return PostLookup(None, None, "", ok=False, message=f"郵政 WS HTTP {exc.code}")
    except Exception as exc:  # noqa: BLE001
        return PostLookup(None, None, "", ok=False, message=f"郵政 WS 錯誤：{exc}")


def get_zip_code(addr_str: str) -> PostLookup:
    """呼叫 GetZipCode（備援）。"""
    if not ENABLED:
        return PostLookup(None, None, "", message="郵政 WS 已停用", ok=False)

    key = addr_str.strip()
    cached = _cache_get(key)
    if cached and cached.ok:
        return cached

    body = (
        f'<GetZipCode xmlns="http://tempuri.org/">'
        f"<addrStr>{_xml_escape(key)}</addrStr>"
        f"<address></address>"
        f"</GetZipCode>"
    )
    try:
        xml = _soap_request("GetZipCode", body)
        root = ET.fromstring(xml)
        zipcode = None
        normalized = None
        for el in root.iter():
            if el.tag.endswith("GetZipCodeResult") and el.text:
                zipcode = el.text.strip()
            if el.tag.endswith("address") and el.text:
                normalized = el.text.strip()
        ok = bool(zipcode and re.fullmatch(r"\d{6}", zipcode))
        out = PostLookup(
            zipcode=zipcode,
            normalized=normalized,
            raw=xml[:500],
            source="post_ws",
            ok=ok,
            message="中華郵政 GetZipCode" if ok else "郵政服務無有效郵遞區號",
        )
        if ok:
            _cache_set(key, out)
        return out
    except Exception as exc:  # noqa: BLE001
        return PostLookup(None, None, "", ok=False, message=f"郵政 WS 錯誤：{exc}")


def lookup_post(addr_str: str) -> PostLookup:
    """優先 GetZipAddress，失敗再 GetZipCode。"""
    first = get_zip_address(addr_str)
    if first.ok:
        return first
    second = get_zip_code(addr_str)
    if second.ok:
        return second
    # 回傳較有資訊的那筆
    if first.message:
        return first
    return second


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
