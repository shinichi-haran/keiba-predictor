"""
競馬予想アプリ データ取得・ポイント計算モジュール
対象サイト:
1. netkeiba.com (出馬表・オッズ・レース一覧)
2. uma-x.jp (偏差値: 総合, SP, AG, 実績)
3. keibalab.jp (ウェブ新聞: Ω指数)
4. muryou-keiba-ai.jp (オリジンAI, ウェーブAI)
5. keiba-ai.jp (ATHENA 着順予想)
"""

from __future__ import annotations

import datetime
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

import base64
import zlib

APP_VERSION = "v2.2.0 (2026-10-24)"
CACHE_FILE = Path(__file__).parent / "race_cache.json"
EMBEDDED_CACHE_B64 = "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"


def load_all_cache() -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    if EMBEDDED_CACHE_B64:
        try:
            raw_bytes = zlib.decompress(base64.b64decode(EMBEDDED_CACHE_B64))
            merged.update(json.loads(raw_bytes.decode("utf-8")))
        except Exception:
            pass
    if CACHE_FILE.exists():
        try:
            merged.update(json.loads(CACHE_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return merged


def save_all_cache(cache_data: Dict[str, Any]) -> None:
    try:
        CACHE_FILE.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# JRA競馬場コードと名称・英語スラッグの対応
VENUE_MAP: Dict[str, Tuple[str, str]] = {
    "01": ("札幌", "sapporo"),
    "02": ("函館", "hakodate"),
    "03": ("福島", "fukushima"),
    "04": ("新潟", "niigata"),
    "05": ("東京", "tokyo"),
    "06": ("中山", "nakayama"),
    "07": ("中京", "chukyo"),
    "08": ("京都", "kyoto"),
    "09": ("阪神", "hanshin"),
    "10": ("小倉", "kokura"),
}

POINT_TABLE = {1: 10, 2: 6, 3: 4, 4: 3, 5: 2, 6: 1}


@dataclass
class RaceMeta:
    race_id: str  # netkeiba 12桁 race_id (YYYYPPKKDDRR)
    kaisai_date: str  # YYYYMMDD
    venue_code: str  # 01..10
    venue_name: str  # 東京, 京都, etc.
    venue_slug: str  # tokyo, kyoto, etc.
    kai: str  # 04
    day: str  # 08
    race_num: int  # 1..12
    race_name: str = ""
    start_time: str = ""
    course_info: str = ""
    weather: str = ""
    track_condition: str = ""
    sub_info: str = ""


@dataclass
class SiteStatus:
    site_name: str
    url: str = ""
    success: bool = False
    message: str = ""


def normalize_horse_name(name: str) -> str:
    """馬名の正規化（空白・記号除去、全角カナ統一）"""
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name)
    s = re.sub(r"[\s　・☆★◎○▲△×注消\(\)（）\[\]「」]", "", s)
    return s.strip()


def assign_points(
    values_by_umaban: Dict[int, Optional[float]],
    higher_is_better: bool = True,
    min_exclusive_threshold: Optional[float] = None,
) -> Dict[int, int]:
    """
    各馬番の数値辞書から上位1〜6位に 10, 6, 4, 3, 2, 1 ポイントを付与する。
    - min_exclusive_threshold が指定されている場合、その値以下 (<= threshold) は対象外 (0pt)。
      例: UMA-Xで min_exclusive_threshold=45.0 の場合、45以下は0pt。
    - 同率順位がある場合は同順位のポイントを全員に付与し、次順位は頭数分スキップする。
    """
    points: Dict[int, int] = {u: 0 for u in values_by_umaban}

    valid_items: List[Tuple[int, float]] = []
    for umaban, val in values_by_umaban.items():
        if val is None or pd.isna(val):
            continue
        if min_exclusive_threshold is not None and val <= min_exclusive_threshold:
            continue
        valid_items.append((umaban, float(val)))

    if not valid_items:
        return points

    valid_items.sort(key=lambda x: x[1], reverse=higher_is_better)

    current_rank = 1
    prev_val: Optional[float] = None
    for idx, (umaban, val) in enumerate(valid_items):
        if idx == 0:
            current_rank = 1
        else:
            if abs(val - prev_val) > 1e-9:
                current_rank = idx + 1
        prev_val = val
        points[umaban] = POINT_TABLE.get(current_rank, 0)

    return points


class KeibaScraper:
    def __init__(
        self,
        netkeiba_cookie: str = "",
        keibalab_cookie: str = "",
        timeout: int = 12,
    ):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.netkeiba_cookie = netkeiba_cookie.strip()
        self.keibalab_cookie = keibalab_cookie.strip()
        self.timeout = timeout

    def _get(self, url: str, cookie: str = "", encoding: Optional[str] = None) -> requests.Response:
        headers = {}
        if cookie:
            headers["Cookie"] = cookie
        resp = self.session.get(url, headers=headers, timeout=self.timeout)
        return resp

    def login_netkeiba(self, login_id: str, password: str) -> Tuple[bool, str]:
        """netkeiba.com にログインしてセッションCookieを保持する"""
        if not login_id or not password:
            return False, "IDまたはパスワードが空です"
        try:
            url = "https://regist.netkeiba.com/"
            data = {
                "pid": "login",
                "action": "auth",
                "rtn_url": "https://race.netkeiba.com/",
                "login_id": login_id,
                "pswd": password,
            }
            resp = self.session.post(url, data=data, timeout=self.timeout, allow_redirects=True)
            cookies_dict = self.session.cookies.get_dict()
            if any("nkauth" in k or "netkeiba" in k for k in cookies_dict):
                return True, "netkeiba ログイン成功"
            if "ログイン" not in self._decode_html(resp) or resp.status_code == 200:
                return True, "netkeiba リクエスト完了"
            return False, "ログイン情報を確認してください"
        except Exception as e:
            return False, f"ログインエラー: {e}"

    def login_keibalab(self, email: str, password: str) -> Tuple[bool, str]:
        """keibalab.jp にログインしてセッションCookieを保持する"""
        if not email or not password:
            return False, "メールアドレスまたはパスワードが空です"
        try:
            url = "https://www.keibalab.jp/login/login.html"
            data = {
                "email": email,
                "pass": password,
                "commit": "ログイン",
            }
            resp = self.session.post(url, data=data, timeout=self.timeout, allow_redirects=True)
            html = self._decode_html(resp)
            if "ログアウト" in html or "マイページ" in html:
                return True, "競馬ラボ ログイン成功"
            return True, "競馬ラボ ログイン送信完了"
        except Exception as e:
            return False, f"ログインエラー: {e}"

    @staticmethod
    def _decode_html(resp: requests.Response) -> str:
        content = resp.content
        # Content-Type or meta check
        ctype = resp.headers.get("Content-Type", "").lower()
        if "utf-8" in ctype:
            return content.decode("utf-8", errors="replace")
        if "euc-jp" in ctype:
            return content.decode("euc-jp", errors="replace")
        # Try utf-8 first, fallback to euc-jp/cp932
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return content.decode("euc-jp")
            except UnicodeDecodeError:
                return content.decode("cp932", errors="replace")

    # ------------------------------------------------------------------
    # 0. Netkeiba 開催日・レース一覧取得
    # ------------------------------------------------------------------
    def get_kaisai_dates(self, target_date: Optional[datetime.date] = None) -> List[str]:
        """指定日周辺の開催日リスト (YYYYMMDD) を取得"""
        if target_date is None:
            jst = datetime.timezone(datetime.timedelta(hours=9))
            target_date = datetime.datetime.now(jst).date()
        date_str = target_date.strftime("%Y%m%d")
        url = f"https://race.netkeiba.com/top/race_list_get_date_list.html?kaisai_date={date_str}&encoding=UTF-8"
        dates = set()
        try:
            resp = self._get(url, cookie=self.netkeiba_cookie)
            text = self._decode_html(resp)
            for m in re.finditer(r"kaisai_date=(\d{8})", text):
                dates.add(m.group(1))
            for m in re.finditer(r'date="(\d{8})"', text):
                dates.add(m.group(1))
        except Exception:
            pass
        dates.add(date_str)
        return sorted(dates)

    def get_races_for_date(self, kaisai_date: str) -> List[RaceMeta]:
        """
        指定した開催日 (YYYYMMDD) の全レース一覧を netkeiba から取得する。
        """
        url = f"https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={kaisai_date}"
        resp = self._get(url, cookie=self.netkeiba_cookie)
        if resp.status_code != 200:
            return []
        html = self._decode_html(resp)
        soup = BeautifulSoup(html, "html.parser")

        races_by_id: Dict[str, RaceMeta] = {}
        for a in soup.find_all("a", href=re.compile(r"race_id=\d{12}")):
            href = a.get("href", "")
            m = re.search(r"race_id=(\d{12})", href)
            if not m:
                continue
            rid = m.group(1)
            # movie.html リンクはテキストが空なのでスキップまたは補完
            text = a.get_text(" ", strip=True)
            if not text and rid in races_by_id:
                continue

            year = rid[0:4]
            venue_code = rid[4:6]
            kai = rid[6:8]
            day = rid[8:10]
            race_num = int(rid[10:12])
            venue_name, venue_slug = VENUE_MAP.get(venue_code, (f"場{venue_code}", "unknown"))

            # リンク内の要素からレース名・発走時刻・コース距離を抽出
            r_name = ""
            item_title = a.select_one(".ItemTitle")
            if item_title:
                r_name = item_title.get_text(strip=True)
            start_t = ""
            time_el = a.select_one(".RaceList_Itemtime")
            if time_el:
                start_t = time_el.get_text(strip=True)
            course_str = ""
            long_el = a.select_one(".RaceList_ItemLong")
            if long_el:
                course_str = long_el.get_text(strip=True)

            if rid not in races_by_id or r_name:
                races_by_id[rid] = RaceMeta(
                    race_id=rid,
                    kaisai_date=kaisai_date,
                    venue_code=venue_code,
                    venue_name=venue_name,
                    venue_slug=venue_slug,
                    kai=kai,
                    day=day,
                    race_num=race_num,
                    race_name=r_name,
                    start_time=start_t,
                    course_info=course_str,
                )

        return sorted(races_by_id.values(), key=lambda r: (r.venue_code, r.race_num))

    # ------------------------------------------------------------------
    # ① Netkeiba 出馬表取得
    # ------------------------------------------------------------------
    def fetch_netkeiba_shutuba(
        self, race_id: str, kaisai_date_hint: str = ""
    ) -> Tuple[Optional[RaceMeta], pd.DataFrame, SiteStatus]:
        url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
        status = SiteStatus(site_name="netkeiba (出馬表)", url=url)
        try:
            resp = self._get(url, cookie=self.netkeiba_cookie)
            if resp.status_code != 200:
                status.message = f"HTTP {resp.status_code}"
                return None, pd.DataFrame(), status

            html = self._decode_html(resp)
            soup = BeautifulSoup(html, "html.parser")

            # 開催日の特定 (タイトルや選択タブから)
            kaisai_date = kaisai_date_hint
            if not kaisai_date:
                title_text = soup.title.get_text(strip=True) if soup.title else ""
                m_date = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", title_text)
                if m_date:
                    kaisai_date = f"{int(m_date.group(1)):04d}{int(m_date.group(2)):02d}{int(m_date.group(3)):02d}"
                else:
                    active_dd = soup.select_one("dd.Active a[href*='kaisai_date=']")
                    if active_dd:
                        m_kd = re.search(r"kaisai_date=(\d{8})", active_dd.get("href", ""))
                        if m_kd:
                            kaisai_date = m_kd.group(1)

            year = race_id[0:4]
            venue_code = race_id[4:6]
            kai = race_id[6:8]
            day = race_id[8:10]
            race_num = int(race_id[10:12])
            venue_name, venue_slug = VENUE_MAP.get(venue_code, (f"場{venue_code}", "unknown"))

            rname_el = soup.select_one(".RaceName")
            race_name = rname_el.get_text(strip=True) if rname_el else f"{race_num}R"

            rdata01_el = soup.select_one(".RaceData01")
            rdata01_text = rdata01_el.get_text(" ", strip=True) if rdata01_el else ""
            rdata02_el = soup.select_one(".RaceData02")
            rdata02_text = rdata02_el.get_text(" ", strip=True) if rdata02_el else ""

            m_time = re.search(r"(\d{1,2}:\d{2})発走", rdata01_text)
            start_time = m_time.group(1) if m_time else ""
            m_course = re.search(r"([芝ダ障][^/]+)", rdata01_text)
            course_info = m_course.group(1).strip() if m_course else ""
            m_weather = re.search(r"天候:([^\s/]+)", rdata01_text)
            weather = m_weather.group(1).strip() if m_weather else ""
            m_cond = re.search(r"馬場:([^\s/]+)", rdata01_text)
            track_cond = m_cond.group(1).strip() if m_cond else ""

            meta = RaceMeta(
                race_id=race_id,
                kaisai_date=kaisai_date,
                venue_code=venue_code,
                venue_name=venue_name,
                venue_slug=venue_slug,
                kai=kai,
                day=day,
                race_num=race_num,
                race_name=race_name,
                start_time=start_time,
                course_info=course_info,
                weather=weather,
                track_condition=track_cond,
                sub_info=rdata02_text,
            )

            # オッズAPIから単勝オッズ・人気を取得
            odds_map: Dict[int, Tuple[Optional[float], Optional[int]]] = {}
            try:
                odds_url = (
                    f"https://race.netkeiba.com/api/api_get_jra_odds.html"
                    f"?race_id={race_id}&type=1&action=init&compress=0"
                )
                odds_resp = self._get(odds_url, cookie=self.netkeiba_cookie)
                if odds_resp.status_code == 200:
                    odds_json = odds_resp.json()
                    tansho = odds_json.get("data", {}).get("odds", {}).get("1", {})
                    for k, v in tansho.items():
                        if isinstance(v, list) and len(v) >= 3:
                            u_num = int(k)
                            try:
                                o_val = float(str(v[0]).replace(",", ""))
                            except ValueError:
                                o_val = None
                            try:
                                n_val = int(v[2])
                            except ValueError:
                                n_val = None
                            odds_map[u_num] = (o_val, n_val)
            except Exception:
                pass

            # 馬一覧の抽出
            rows_data = []
            for tr in soup.select("tr.HorseList"):
                waku_td = tr.select_one('td[class^="Waku"]')
                umaban_td = tr.select_one('td[class^="Umaban"]')
                if not umaban_td:
                    continue
                umaban_txt = umaban_td.get_text(strip=True)
                if not umaban_txt.isdigit():
                    continue
                umaban = int(umaban_txt)
                waku = int(waku_td.get_text(strip=True)) if (waku_td and waku_td.get_text(strip=True).isdigit()) else 0

                hname_el = tr.select_one(".HorseName a") or tr.select_one(".HorseName")
                horse_name = hname_el.get_text(strip=True) if hname_el else ""

                barei_el = tr.select_one(".Barei")
                sex_age = barei_el.get_text(strip=True) if barei_el else ""

                # 斤量
                tds = tr.find_all("td")
                kinryo = tds[5].get_text(strip=True) if len(tds) > 5 else ""

                jockey_el = tr.select_one(".Jockey a") or tr.select_one(".Jockey")
                jockey = jockey_el.get_text(strip=True) if jockey_el else ""

                trainer_el = tr.select_one(".Trainer a") or tr.select_one(".Trainer")
                trainer = trainer_el.get_text(strip=True) if trainer_el else ""

                weight_el = tr.select_one(".Weight")
                horse_weight = weight_el.get_text(strip=True) if weight_el else ""

                is_scratched = "Cancel" in (tr.get("class") or [])

                odds_val, ninki_val = odds_map.get(umaban, (None, None))

                rows_data.append(
                    {
                        "枠番": waku,
                        "馬番": umaban,
                        "馬名": horse_name,
                        "馬名正規化": normalize_horse_name(horse_name),
                        "性齢": sex_age,
                        "斤量": kinryo,
                        "騎手": jockey,
                        "厩舎": trainer,
                        "馬体重": horse_weight,
                        "単勝オッズ": odds_val,
                        "人気": ninki_val,
                        "取消": is_scratched,
                    }
                )

            df = pd.DataFrame(rows_data)
            if df.empty:
                status.message = "出馬表データが見つかりませんでした"
                return meta, df, status

            status.success = True
            status.message = f"{len(df)}頭取得完了"
            return meta, df, status

        except Exception as e:
            status.message = f"取得エラー: {e}"
            return None, pd.DataFrame(), status

    # ------------------------------------------------------------------
    # ② UMA-X 偏差値 (総合, SP, AG, 実績) 取得
    # ------------------------------------------------------------------
    def fetch_umax(self, meta: RaceMeta) -> Tuple[Dict[int, Dict[str, Optional[float]]], SiteStatus]:
        """
        UMA-Xから各馬の偏差値 (総合, SP, AG, 実績) を取得。
        戻り値: {馬番: {"UMA_総合": float, "UMA_SP": float, "UMA_AG": float, "UMA_実績": float}}
        """
        year = meta.race_id[0:4]
        venue_int = int(meta.venue_code)
        umax_id = f"{venue_int}{year}{meta.kai}{meta.day}{meta.race_num:02d}{meta.kaisai_date}"
        url = f"https://uma-x.jp/race_result/{umax_id}"
        status = SiteStatus(site_name="UMA-X (偏差値)", url=url)
        result: Dict[int, Dict[str, Optional[float]]] = {}

        try:
            resp = self._get(url)
            if resp.status_code != 200:
                status.message = f"HTTP {resp.status_code} (データ未公開またはURL不一致)"
                return result, status

            html = self._decode_html(resp)
            soup = BeautifulSoup(html, "html.parser")

            target_table = None
            for t in soup.find_all("table"):
                first_tr = t.find("tr")
                if not first_tr:
                    continue
                headers = [c.get_text(strip=True) for c in first_tr.find_all(["th", "td"])]
                if "総合" in headers and "SP" in headers and "AG" in headers and "実績" in headers:
                    target_table = t
                    break

            if not target_table:
                status.message = "偏差値テーブル(総合/SP/AG/実績)が見つかりませんでした"
                return result, status

            trs = target_table.find_all("tr")
            header_cols = [c.get_text(strip=True) for c in trs[0].find_all(["th", "td"])]
            idx_total = header_cols.index("総合")
            idx_sp = header_cols.index("SP")
            idx_ag = header_cols.index("AG")
            idx_ach = header_cols.index("実績")

            for tr in trs[1:]:
                cols = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
                if len(cols) <= max(idx_total, idx_sp, idx_ag, idx_ach):
                    continue
                # 先頭列は "1タプティ" のような形式（馬番＋馬名）
                m_num = re.match(r"^(\d+)", cols[0])
                if not m_num:
                    continue
                umaban = int(m_num.group(1))

                def _parse_val(s: str) -> Optional[float]:
                    m_v = re.search(r"[-+]?\d+(?:\.\d+)?", s)
                    return float(m_v.group(0)) if m_v else None

                result[umaban] = {
                    "UMA_総合": _parse_val(cols[idx_total]),
                    "UMA_SP": _parse_val(cols[idx_sp]),
                    "UMA_AG": _parse_val(cols[idx_ag]),
                    "UMA_実績": _parse_val(cols[idx_ach]),
                }

            if result:
                status.success = True
                status.message = f"{len(result)}頭の偏差値を取得"
            else:
                status.message = "偏差値データが0件でした"
            return result, status

        except Exception as e:
            status.message = f"取得エラー: {e}"
            return result, status

    # ------------------------------------------------------------------
    # ②-2 競馬ラボ (keibalab.jp) ウェブ新聞 Ω指数取得
    # ------------------------------------------------------------------
    def fetch_keibalab_omega(self, meta: RaceMeta) -> Tuple[Dict[int, Optional[float]], SiteStatus]:
        """
        競馬ラボのウェブ新聞から各馬のΩ指数を取得。
        URL: https://www.keibalab.jp/db/race/{YYYYMMDD}{PP}{RR}/umabashira.html
        """
        klab_id = f"{meta.kaisai_date}{meta.venue_code}{meta.race_num:02d}"
        url = f"https://www.keibalab.jp/db/race/{klab_id}/umabashira.html"
        status = SiteStatus(site_name="競馬ラボ (Ω指数)", url=url)
        result: Dict[int, Optional[float]] = {}

        try:
            resp = self._get(url, cookie=self.keibalab_cookie)
            if resp.status_code != 200:
                status.message = f"HTTP {resp.status_code}"
                return result, status

            html = self._decode_html(resp)
            soup = BeautifulSoup(html, "html.parser")

            tate_table = soup.select_one("table.megamoriTable")
            if not tate_table:
                status.message = "ウェブ新聞テーブルが見つかりませんでした"
                return result, status

            umaban_cells: List[str] = []
            omega_cells: List[str] = []

            for tr in tate_table.find_all("tr"):
                th = tr.find("th")
                label = th.get_text(strip=True) if th else ""
                if label == "馬番" or "馬番" in label:
                    tds = [td.get_text(strip=True) for td in tr.find_all("td")]
                    if any(t.isdigit() for t in tds):
                        umaban_cells = tds
                if "Ω指数" in label:
                    omega_cells = [td.get_text(strip=True) for td in tr.find_all("td")]

            if not umaban_cells or not omega_cells:
                status.message = "馬番またはΩ指数行が見つかりませんでした"
                return result, status

            # 末尾側からペアリング（先頭に空セルがあるため）
            nums = [x for x in umaban_cells if x.isdigit()]
            omegas = [x for x in omega_cells if x != ""]

            if len(nums) == len(omegas):
                pairs = zip(nums, omegas)
            else:
                pairs = zip(umaban_cells, omega_cells)

            for u_str, o_str in pairs:
                if not u_str.isdigit():
                    continue
                u_num = int(u_str)
                m_val = re.search(r"\d+(?:\.\d+)?", o_str)
                val = float(m_val.group(0)) if m_val else None
                # 0 または未算出は None 扱い
                if val is not None and val <= 0:
                    val = None
                result[u_num] = val

            valid_count = sum(1 for v in result.values() if v is not None)
            if valid_count > 0:
                status.success = True
                status.message = f"{valid_count}頭のΩ指数を取得"
            else:
                status.message = "Ω指数が未公開または算出対象外です"
            return result, status

        except Exception as e:
            status.message = f"取得エラー: {e}"
            return result, status

    _muryou_page_html_cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # ③ 無料競馬AI (muryou-keiba-ai.jp) オリジンAI・ウェーブAI 取得
    # ------------------------------------------------------------------
    def _find_muryou_ai_url(self, meta: RaceMeta) -> Optional[str]:
        """
        開催日・競馬場・レース番号から muryou-keiba-ai.jp の個別予想ページURLを特定する。
        リンク文字列例: "東京 10月24日 11R 15:45 アルテミスステークス..."
        """
        year = int(meta.kaisai_date[0:4])
        month = int(meta.kaisai_date[4:6])
        day = int(meta.kaisai_date[6:8])

        # 検索パターン: "東京 10月24日 11R"
        pattern = re.compile(
            rf"{re.escape(meta.venue_name)}\s*{month}月{day}日\s*{meta.race_num}R(?:\D|$)"
        )

        candidate_list_urls = [
            "https://muryou-keiba-ai.jp/",
            f"https://muryou-keiba-ai.jp/predict/course/{meta.venue_slug}/",
            f"https://muryou-keiba-ai.jp/predict/?y={year}&month={month:02d}",
            f"https://muryou-keiba-ai.jp/predict/course/{meta.venue_slug}/page/2/",
        ]

        for list_url in candidate_list_urls:
            try:
                if list_url in KeibaScraper._muryou_page_html_cache:
                    html = KeibaScraper._muryou_page_html_cache[list_url]
                else:
                    resp = self._get(list_url)
                    if resp.status_code != 200:
                        continue
                    html = self._decode_html(resp)
                    KeibaScraper._muryou_page_html_cache[list_url] = html
                soup = BeautifulSoup(html, "html.parser")
                for a in soup.find_all("a", href=re.compile(r"/predict/\d{4}/\d{2}/\d{2}/\d+/")):
                    text = a.get_text(" ", strip=True)
                    if pattern.search(text):
                        href = a.get("href", "")
                        m_yr = re.search(r"/predict/(\d{4})/", href)
                        if m_yr and abs(int(m_yr.group(1)) - year) <= 1:
                            return href
            except Exception:
                continue

        return None

    @staticmethod
    def _parse_muryou_ai_table(soup: BeautifulSoup) -> Dict[int, Optional[float]]:
        scores: Dict[int, Optional[float]] = {}
        table = soup.select_one("table.baken_race_table") or soup.select_one("table.race_table")
        if not table:
            return scores
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 4:
                continue
            u_txt = tds[0].get_text(strip=True)
            if not u_txt.isdigit():
                continue
            umaban = int(u_txt)
            score_txt = tds[3].get_text(strip=True)
            m_val = re.search(r"\d+(?:\.\d+)?", score_txt)
            scores[umaban] = float(m_val.group(0)) if m_val else None
        return scores

    def fetch_muryou_ai(
        self, meta: RaceMeta
    ) -> Tuple[Dict[int, Optional[float]], Dict[int, Optional[float]], SiteStatus]:
        """
        無料競馬AIからオリジンAI・ウェーブAIの指数を取得。
        戻り値: (origin_scores, wave_scores, status)
        """
        status = SiteStatus(site_name="無料競馬AI (オリジン/ウェーブ)")
        origin_scores: Dict[int, Optional[float]] = {}
        wave_scores: Dict[int, Optional[float]] = {}

        try:
            race_url = self._find_muryou_ai_url(meta)
            if not race_url:
                status.message = "該当レースの予想ページが見つかりませんでした（未公開の可能性）"
                return origin_scores, wave_scores, status

            status.url = race_url
            resp = self._get(race_url)
            if resp.status_code != 200:
                status.message = f"HTTP {resp.status_code}"
                return origin_scores, wave_scores, status

            html = self._decode_html(resp)
            soup = BeautifulSoup(html, "html.parser")
            origin_scores = self._parse_muryou_ai_table(soup)

            # ウェーブAIのリンクを取得
            wave_link = soup.select_one("a.ai_tab.wave")
            if wave_link and wave_link.get("href"):
                wave_url = wave_link.get("href")
                resp_w = self._get(wave_url)
                if resp_w.status_code == 200:
                    soup_w = BeautifulSoup(self._decode_html(resp_w), "html.parser")
                    wave_scores = self._parse_muryou_ai_table(soup_w)

            if origin_scores or wave_scores:
                status.success = True
                status.message = f"オリジン:{len(origin_scores)}頭 / ウェーブ:{len(wave_scores)}頭 取得"
            else:
                status.message = "AI予想テーブルの数値が見つかりませんでした"
            return origin_scores, wave_scores, status

        except Exception as e:
            status.message = f"取得エラー: {e}"
            return origin_scores, wave_scores, status

    _keiba_ai_page_html_cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # ④ keiba-ai.jp (AI ATHENA) 着順予想取得
    # ------------------------------------------------------------------
    def fetch_keiba_ai(
        self, meta: RaceMeta
    ) -> Tuple[Dict[int, Optional[float]], Dict[int, str], SiteStatus]:
        """
        keiba-ai.jp から着順予想（1位, 2位...）および参考AI指数を取得。
        戻り値: (pred_rank_by_umaban, ai_index_str_by_umaban, status)
        """
        year = meta.kaisai_date[0:4]
        month = meta.kaisai_date[4:6]
        day = meta.kaisai_date[6:8]
        panel_id = f"p-{meta.venue_slug}-{meta.race_num}"
        url = f"https://keiba-ai.jp/predictions/{year}/{month}/{day}/#{meta.venue_slug}"
        page_url = f"https://keiba-ai.jp/predictions/{year}/{month}/{day}/"
        status = SiteStatus(site_name="keiba-ai.jp (着順予想)", url=url)

        pred_ranks: Dict[int, Optional[float]] = {}
        ai_indices: Dict[int, str] = {}

        try:
            if page_url in KeibaScraper._keiba_ai_page_html_cache:
                html = KeibaScraper._keiba_ai_page_html_cache[page_url]
            else:
                resp = self._get(page_url)
                if resp.status_code != 200:
                    status.message = f"HTTP {resp.status_code} (当日予想未公開の可能性)"
                    return pred_ranks, ai_indices, status
                html = self._decode_html(resp)
                KeibaScraper._keiba_ai_page_html_cache[page_url] = html
            soup = BeautifulSoup(html, "html.parser")

            panel = soup.find("div", id=panel_id)
            if not panel:
                # フォールバック: venue セクション内の "{race_num}R" を探す
                venue_sec = soup.find("section", id=meta.venue_slug)
                if venue_sec:
                    for p in venue_sec.select("div.race-panel"):
                        rno = p.select_one(".race-no")
                        if rno and rno.get_text(strip=True) == f"{meta.race_num}R":
                            panel = p
                            break

            if not panel:
                status.message = f"{meta.venue_name}{meta.race_num}R のパネルが見つかりませんでした"
                return pred_ranks, ai_indices, status

            table = panel.select_one("table.entries")
            if not table:
                status.message = "出馬表(entries)が見つかりませんでした"
                return pred_ranks, ai_indices, status

            trs = table.find_all("tr")
            if not trs:
                return pred_ranks, ai_indices, status

            headers = [c.get_text(strip=True) for c in trs[0].find_all(["th", "td"])]
            idx_umaban = 0
            idx_pred = -1
            idx_ai = -1
            for i, h in enumerate(headers):
                if "馬番" in h:
                    idx_umaban = i
                elif "着順予想" in h:
                    idx_pred = i
                elif "AI指数" in h:
                    idx_ai = i

            if idx_pred == -1:
                idx_pred = 5

            for tr in trs[1:]:
                tds = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
                if len(tds) <= idx_pred:
                    continue
                u_str = tds[idx_umaban]
                if not u_str.isdigit():
                    continue
                umaban = int(u_str)

                pred_str = tds[idx_pred]
                m_rank = re.search(r"\d+", pred_str)
                pred_ranks[umaban] = float(m_rank.group(0)) if m_rank else None

                if idx_ai != -1 and len(tds) > idx_ai:
                    ai_indices[umaban] = tds[idx_ai]

            if pred_ranks:
                status.success = True
                status.message = f"{len(pred_ranks)}頭の着順予想を取得"
            else:
                status.message = "着順予想データが0件でした"
            return pred_ranks, ai_indices, status

        except Exception as e:
            status.message = f"取得エラー: {e}"
            return pred_ranks, ai_indices, status

    # ------------------------------------------------------------------
    # ⑤ 全サイト統合・ポイント計算・ソート処理
    # ------------------------------------------------------------------
    def analyze_race(
        self, race_id: str, kaisai_date_hint: str = ""
    ) -> Tuple[Optional[RaceMeta], pd.DataFrame, List[SiteStatus]]:
        """
        指定した race_id について全5サイトからデータを取得し、
        8項目のポイント付与と合計ポイント算出を行った DataFrame を返す。
        """
        statuses: List[SiteStatus] = []

        # ① netkeiba 出馬表
        meta, df, st_nk = self.fetch_netkeiba_shutuba(race_id, kaisai_date_hint)
        statuses.append(st_nk)
        if meta is None or df.empty:
            return meta, df, statuses

        umabans: List[int] = df["馬番"].tolist()
        scratched_set = set(df.loc[df["取消"] == True, "馬番"].tolist())

        all_cache = load_all_cache()
        race_cached = all_cache.get(race_id, {})
        cache_updated = False

        # ② UMA-X 偏差値 (総合, SP, AG, 実績)
        if race_cached.get("umax"):
            umax_data = {int(k): v for k, v in race_cached["umax"].items()}
            year = meta.race_id[0:4]
            umax_id = f"{int(meta.venue_code)}{year}{meta.kai}{meta.day}{meta.race_num:02d}{meta.kaisai_date}"
            st_umax = SiteStatus(
                site_name="UMA-X (偏差値)",
                url=f"https://uma-x.jp/race_result/{umax_id}",
                success=True,
                message=f"{len(umax_data)}頭の偏差値を取得(キャッシュ)",
            )
        else:
            umax_data, st_umax = self.fetch_umax(meta)
            if st_umax.success and umax_data:
                race_cached["umax"] = {str(k): v for k, v in umax_data.items()}
                cache_updated = True
        statuses.append(st_umax)

        # ②-2 競馬ラボ Ω指数
        if race_cached.get("omega"):
            omega_data = {int(k): v for k, v in race_cached["omega"].items()}
            klab_id = f"{meta.kaisai_date}{meta.venue_code}{meta.race_num:02d}"
            st_klab = SiteStatus(
                site_name="競馬ラボ (Ω指数)",
                url=f"https://www.keibalab.jp/db/race/{klab_id}/umabashira.html",
                success=True,
                message=f"{len(omega_data)}頭のΩ指数を取得(キャッシュ)",
            )
        else:
            omega_data, st_klab = self.fetch_keibalab_omega(meta)
            if st_klab.success and omega_data:
                race_cached["omega"] = {str(k): v for k, v in omega_data.items()}
                cache_updated = True
        statuses.append(st_klab)

        # ③ 無料競馬AI (オリジンAI, ウェーブAI)
        if race_cached.get("origin") or race_cached.get("wave"):
            origin_data = {int(k): v for k, v in race_cached.get("origin", {}).items()}
            wave_data = {int(k): v for k, v in race_cached.get("wave", {}).items()}
            st_mai = SiteStatus(
                site_name="無料競馬AI (オリジン/ウェーブ)",
                url=race_cached.get("muryou_url", "https://muryou-keiba-ai.jp/"),
                success=True,
                message=f"オリジン:{len(origin_data)}頭 / ウェーブ:{len(wave_data)}頭 取得(キャッシュ)",
            )
        else:
            origin_data, wave_data, st_mai = self.fetch_muryou_ai(meta)
            if st_mai.success and (origin_data or wave_data):
                race_cached["origin"] = {str(k): v for k, v in origin_data.items()}
                race_cached["wave"] = {str(k): v for k, v in wave_data.items()}
                race_cached["muryou_url"] = st_mai.url
                cache_updated = True
        statuses.append(st_mai)

        # ④ keiba-ai.jp (着順予想) - クラウドからも直接取得可能だがキャッシュもフォールバック保持
        athena_ranks, athena_ai_str, st_kai = self.fetch_keiba_ai(meta)
        if st_kai.success and athena_ranks:
            race_cached["athena_ranks"] = {str(k): v for k, v in athena_ranks.items()}
            race_cached["athena_ai_str"] = {str(k): v for k, v in athena_ai_str.items()}
            cache_updated = True
        elif race_cached.get("athena_ranks"):
            athena_ranks = {int(k): v for k, v in race_cached["athena_ranks"].items()}
            athena_ai_str = {int(k): v for k, v in race_cached.get("athena_ai_str", {}).items()}
            st_kai.success = True
            st_kai.message = f"{len(athena_ranks)}頭の着順予想を取得(キャッシュ)"
        statuses.append(st_kai)

        if cache_updated:
            all_cache[race_id] = race_cached
            save_all_cache(all_cache)

        # 各項目の生データを馬番辞書に整理 (取消馬はポイント計算から除外するためランク用辞書ではNoneにする)
        raw_uma_total = {u: umax_data.get(u, {}).get("UMA_総合") for u in umabans}
        raw_uma_sp = {u: umax_data.get(u, {}).get("UMA_SP") for u in umabans}
        raw_uma_ag = {u: umax_data.get(u, {}).get("UMA_AG") for u in umabans}
        raw_uma_ach = {u: umax_data.get(u, {}).get("UMA_実績") for u in umabans}
        raw_omega = {u: omega_data.get(u) for u in umabans}
        raw_origin = {u: origin_data.get(u) for u in umabans}
        raw_wave = {u: wave_data.get(u) for u in umabans}
        raw_athena = {u: athena_ranks.get(u) for u in umabans}

        def _active_only(d: Dict[int, Optional[float]]) -> Dict[int, Optional[float]]:
            return {u: (None if u in scratched_set else v) for u, v in d.items()}

        # 各項目のポイント計算
        # UMA-Xは偏差値45以下にはポイント付与を行わない (min_exclusive_threshold=45.0)
        pt_uma_total = assign_points(_active_only(raw_uma_total), higher_is_better=True, min_exclusive_threshold=45.0)
        pt_uma_sp = assign_points(_active_only(raw_uma_sp), higher_is_better=True, min_exclusive_threshold=45.0)
        pt_uma_ag = assign_points(_active_only(raw_uma_ag), higher_is_better=True, min_exclusive_threshold=45.0)
        pt_uma_ach = assign_points(_active_only(raw_uma_ach), higher_is_better=True, min_exclusive_threshold=45.0)

        # 競馬ラボ Ω指数 (降順)
        pt_omega = assign_points(_active_only(raw_omega), higher_is_better=True)

        # 無料競馬AI オリジンAI・ウェーブAI (降順)
        pt_origin = assign_points(_active_only(raw_origin), higher_is_better=True)
        pt_wave = assign_points(_active_only(raw_wave), higher_is_better=True)

        # keiba-ai.jp 着順予想 (1位, 2位... なので昇順 higher_is_better=False)
        pt_athena = assign_points(_active_only(raw_athena), higher_is_better=False)

        # DataFrame に各列を追加
        df["UMA総合_値"] = df["馬番"].map(raw_uma_total)
        df["UMA総合_pt"] = df["馬番"].map(pt_uma_total)

        df["UMASP_値"] = df["馬番"].map(raw_uma_sp)
        df["UMASP_pt"] = df["馬番"].map(pt_uma_sp)

        df["UMAAG_値"] = df["馬番"].map(raw_uma_ag)
        df["UMAAG_pt"] = df["馬番"].map(pt_uma_ag)

        df["UMA実績_値"] = df["馬番"].map(raw_uma_ach)
        df["UMA実績_pt"] = df["馬番"].map(pt_uma_ach)

        df["Ω指数_値"] = df["馬番"].map(raw_omega)
        df["Ω指数_pt"] = df["馬番"].map(pt_omega)

        df["オリジンAI_値"] = df["馬番"].map(raw_origin)
        df["オリジンAI_pt"] = df["馬番"].map(pt_origin)

        df["ウェーブAI_値"] = df["馬番"].map(raw_wave)
        df["ウェーブAI_pt"] = df["馬番"].map(pt_wave)

        df["着順予想_値"] = df["馬番"].map(raw_athena)
        df["着順予想_指数"] = df["馬番"].map(lambda u: athena_ai_str.get(u, ""))
        df["着順予想_pt"] = df["馬番"].map(pt_athena)

        pt_cols = [
            "UMA総合_pt",
            "UMASP_pt",
            "UMAAG_pt",
            "UMA実績_pt",
            "Ω指数_pt",
            "オリジンAI_pt",
            "ウェーブAI_pt",
            "着順予想_pt",
        ]
        df["UMA小計_pt"] = (
            df["UMA総合_pt"] + df["UMASP_pt"] + df["UMAAG_pt"] + df["UMA実績_pt"]
        )
        df["AI小計_pt"] = df["オリジンAI_pt"] + df["ウェーブAI_pt"] + df["着順予想_pt"]
        df["合計_pt"] = df[pt_cols].sum(axis=1)

        # 獲得項目数（1pt以上獲得した項目の数 / 8項目中）
        df["獲得項目数"] = (df[pt_cols] > 0).sum(axis=1)

        # 合計ポイント上位順にソート（同点時は獲得項目数降順 -> 馬番昇順）
        df = df.sort_values(
            by=["合計_pt", "獲得項目数", "馬番"], ascending=[False, False, True]
        ).reset_index(drop=True)

        # 総合順位（同点時は同順位）
        ranks = []
        prev_pt = None
        cur_rank = 1
        for i, pt in enumerate(df["合計_pt"]):
            if i == 0:
                cur_rank = 1
            elif pt != prev_pt:
                cur_rank = i + 1
            prev_pt = pt
            ranks.append(cur_rank)
        df.insert(0, "予想順位", ranks)

        return meta, df, statuses
