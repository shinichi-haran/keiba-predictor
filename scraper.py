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
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

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
            f"https://muryou-keiba-ai.jp/predict/course/{meta.venue_slug}/",
            "https://muryou-keiba-ai.jp/",
            f"https://muryou-keiba-ai.jp/predict/?y={year}&month={month:02d}",
            f"https://muryou-keiba-ai.jp/predict/course/{meta.venue_slug}/page/2/",
        ]

        for list_url in candidate_list_urls:
            try:
                resp = self._get(list_url)
                if resp.status_code != 200:
                    continue
                html = self._decode_html(resp)
                soup = BeautifulSoup(html, "html.parser")
                for a in soup.find_all("a", href=re.compile(r"/predict/\d{4}/\d{2}/\d{2}/\d+/")):
                    text = a.get_text(" ", strip=True)
                    if pattern.search(text):
                        href = a.get("href", "")
                        # 念のためURL内の年と対象年が一致するか確認（1月開催で12月投稿等のケースは前後1年許容）
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
            resp = self._get(page_url)
            if resp.status_code != 200:
                status.message = f"HTTP {resp.status_code} (当日予想未公開の可能性)"
                return pred_ranks, ai_indices, status

            html = self._decode_html(resp)
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

        # ② UMA-X 偏差値 (総合, SP, AG, 実績)
        umax_data, st_umax = self.fetch_umax(meta)
        statuses.append(st_umax)

        # ②-2 競馬ラボ Ω指数
        omega_data, st_klab = self.fetch_keibalab_omega(meta)
        statuses.append(st_klab)

        # ③ 無料競馬AI (オリジンAI, ウェーブAI)
        origin_data, wave_data, st_mai = self.fetch_muryou_ai(meta)
        statuses.append(st_mai)

        # ④ keiba-ai.jp (着順予想)
        athena_ranks, athena_ai_str, st_kai = self.fetch_keiba_ai(meta)
        statuses.append(st_kai)

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
