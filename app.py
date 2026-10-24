"""
競馬予想 総合ポイント集計・可視化アプリ (Streamlit ローカルWebアプリ / スマホ対応 / テーマ切替対応)
"""

from __future__ import annotations

import datetime
import io
import json
import re
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import altair as alt
import pandas as pd
import qrcode
import streamlit as st

from scraper import KeibaScraper

# ページ設定
st.set_page_config(
    page_title="競馬予想 マルチ指数＆AI ポイント集計アプリ",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="expanded",
)

CONFIG_PATH = Path(__file__).parent / "user_config.json"

# テーマプリセット定義
THEME_PRESETS: Dict[str, Dict[str, Any]] = {
    "☀️ ライト（標準）": {
        "is_dark": False,
        "bg": "#f8fafc",
        "sidebar_bg": "#ffffff",
        "card_bg": "#ffffff",
        "text": "#0f172a",
        "sub_text": "#475569",
        "muted_text": "#94a3b8",
        "border": "#cbd5e1",
        "table_border": "#e2e8f0",
        "row_hover": "#f1f5f9",
        "sub_col_bg": "#f8fafc",
        "tag_bg": "#f1f5f9",
        "header_grad": "linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%)",
    },
    "🌙 ダーク（ネイビー）": {
        "is_dark": True,
        "bg": "#0f172a",
        "sidebar_bg": "#1e293b",
        "card_bg": "#1e293b",
        "text": "#f8fafc",
        "sub_text": "#cbd5e1",
        "muted_text": "#64748b",
        "border": "#334155",
        "table_border": "#334155",
        "row_hover": "#334155",
        "sub_col_bg": "#0f172a",
        "tag_bg": "#0f172a",
        "header_grad": "linear-gradient(135deg, #020617 0%, #1e3a8a 100%)",
    },
    "🖤 ミッドナイト（純黒ダーク）": {
        "is_dark": True,
        "bg": "#09090b",
        "sidebar_bg": "#18181b",
        "card_bg": "#18181b",
        "text": "#f4f4f5",
        "sub_text": "#a1a1aa",
        "muted_text": "#52525b",
        "border": "#27272a",
        "table_border": "#27272a",
        "row_hover": "#27272a",
        "sub_col_bg": "#121215",
        "tag_bg": "#27272a",
        "header_grad": "linear-gradient(135deg, #18181b 0%, #3f3f46 100%)",
    },
    "🌿 ターフグリーン（芝ダーク）": {
        "is_dark": True,
        "bg": "#051f18",
        "sidebar_bg": "#092e24",
        "card_bg": "#0b382c",
        "text": "#ecfdf5",
        "sub_text": "#a7f3d0",
        "muted_text": "#34d399",
        "border": "#14533e",
        "table_border": "#14533e",
        "row_hover": "#114a39",
        "sub_col_bg": "#072920",
        "tag_bg": "#072920",
        "header_grad": "linear-gradient(135deg, #064e3b 0%, #047857 100%)",
    },
    "📜 セピア（目に優しい暖色）": {
        "is_dark": False,
        "bg": "#f5f0e6",
        "sidebar_bg": "#ece4d5",
        "card_bg": "#fdfbf7",
        "text": "#29201b",
        "sub_text": "#5c4d43",
        "muted_text": "#a39487",
        "border": "#d6cbb9",
        "table_border": "#e3dacb",
        "row_hover": "#efe9dd",
        "sub_col_bg": "#f5f0e6",
        "tag_bg": "#efe9dd",
        "header_grad": "linear-gradient(135deg, #451a03 0%, #78350f 100%)",
    },
}

# 枠番カラー定義 (JRA準拠)
WAKU_STYLE: Dict[int, Tuple[str, str, str]] = {
    1: ("#ffffff", "#1e293b", "#94a3b8"),  # 白
    2: ("#1e293b", "#ffffff", "#475569"),  # 黒
    3: ("#dc2626", "#ffffff", "#dc2626"),  # 赤
    4: ("#2563eb", "#ffffff", "#2563eb"),  # 青
    5: ("#facc15", "#1e293b", "#eab308"),  # 黄
    6: ("#16a34a", "#ffffff", "#16a34a"),  # 緑
    7: ("#ea580c", "#ffffff", "#ea580c"),  # 橙
    8: ("#f472b6", "#ffffff", "#ec4899"),  # 桃
}

# ポイント別バッジ色 (10, 6, 4, 3, 2, 1, 0)
PT_STYLE: Dict[int, Tuple[str, str]] = {
    10: ("#b91c1c", "#ffffff"),  # 1位: 濃赤
    6: ("#ea580c", "#ffffff"),   # 2位: オレンジ
    4: ("#d97706", "#ffffff"),   # 3位: アンバー
    3: ("#0284c7", "#ffffff"),   # 4位: ブルー
    2: ("#38bdf8", "#0f172a"),   # 5位: スカイ
    1: ("#bae6fd", "#0369a1"),   # 6位: 薄水色
    0: ("transparent", "#94a3b8"),
}

ITEM_META = [
    {"col_pt": "UMA総合_pt", "col_val": "UMA総合_値", "label": "UMA-X 総合", "short": "UMA総合", "cat": "UMA-X", "color": "#2563eb"},
    {"col_pt": "UMASP_pt", "col_val": "UMASP_値", "label": "UMA-X SP", "short": "UMA SP", "cat": "UMA-X", "color": "#3b82f6"},
    {"col_pt": "UMAAG_pt", "col_val": "UMAAG_値", "label": "UMA-X AG", "short": "UMA AG", "cat": "UMA-X", "color": "#60a5fa"},
    {"col_pt": "UMA実績_pt", "col_val": "UMA実績_値", "label": "UMA-X 実績", "short": "UMA実績", "cat": "UMA-X", "color": "#93c5fd"},
    {"col_pt": "Ω指数_pt", "col_val": "Ω指数_値", "label": "競馬ラボ Ω指数", "short": "Ω指数", "cat": "競馬ラボ", "color": "#f59e0b"},
    {"col_pt": "オリジンAI_pt", "col_val": "オリジンAI_値", "label": "無料競馬AI オリジン", "short": "オリジンAI", "cat": "無料競馬AI", "color": "#10b981"},
    {"col_pt": "ウェーブAI_pt", "col_val": "ウェーブAI_値", "label": "無料競馬AI ウェーブ", "short": "ウェーブAI", "cat": "無料競馬AI", "color": "#34d399"},
    {"col_pt": "着順予想_pt", "col_val": "着順予想_値", "label": "keiba-ai 着順予想", "short": "着順予想", "cat": "keiba-ai.jp", "color": "#8b5cf6"},
]


def get_local_ip() -> str:
    """PCのLAN内IPアドレスを取得"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def make_qr_png_bytes(url: str) -> bytes:
    """指定URLのQRコードPNGバイト列を生成"""
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def load_user_config() -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "theme_name": "☀️ ライト（標準）",
        "custom_bg": "#1e293b",
        "custom_card": "#334155",
        "custom_text": "#f8fafc",
        "sticky_horse_col": True,
        "netkeiba_id": "",
        "netkeiba_pass": "",
        "netkeiba_cookie": "",
        "keibalab_email": "",
        "keibalab_pass": "",
        "keibalab_cookie": "",
    }
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            defaults.update(loaded)
        except Exception:
            pass
    return defaults


def save_user_config(cfg: Dict[str, Any]) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_scraper(cfg: Dict[str, Any]) -> KeibaScraper:
    scraper = KeibaScraper(
        netkeiba_cookie=cfg.get("netkeiba_cookie", ""),
        keibalab_cookie=cfg.get("keibalab_cookie", ""),
    )
    if cfg.get("netkeiba_id") and cfg.get("netkeiba_pass") and not cfg.get("netkeiba_cookie"):
        scraper.login_netkeiba(cfg["netkeiba_id"], cfg["netkeiba_pass"])
    if cfg.get("keibalab_email") and cfg.get("keibalab_pass") and not cfg.get("keibalab_cookie"):
        scraper.login_keibalab(cfg["keibalab_email"], cfg["keibalab_pass"])
    return scraper


@st.cache_data(ttl=300, show_spinner=False)
def cached_get_races_for_date(kaisai_date: str, nk_cookie: str) -> List[Dict[str, Any]]:
    scraper = KeibaScraper(netkeiba_cookie=nk_cookie)
    races = scraper.get_races_for_date(kaisai_date)
    return [r.__dict__ for r in races]


@st.cache_data(ttl=180, show_spinner=False)
def cached_analyze_race(
    race_id: str,
    kaisai_date_hint: str,
    nk_cookie: str,
    kl_cookie: str,
    nk_id: str,
    nk_pass: str,
    kl_email: str,
    kl_pass: str,
) -> Tuple[Optional[Dict[str, Any]], pd.DataFrame, List[Dict[str, Any]]]:
    cfg = {
        "netkeiba_cookie": nk_cookie,
        "keibalab_cookie": kl_cookie,
        "netkeiba_id": nk_id,
        "netkeiba_pass": nk_pass,
        "keibalab_email": kl_email,
        "keibalab_pass": kl_pass,
    }
    scraper = get_scraper(cfg)
    meta, df, statuses = scraper.analyze_race(race_id, kaisai_date_hint)
    meta_dict = meta.__dict__ if meta else None
    st_list = [s.__dict__ for s in statuses]
    return meta_dict, df, st_list


def inject_theme_css(theme: Dict[str, Any], sticky_horse_col: bool = True) -> None:
    """選択されたテーマ（ダークモード等）およびスマホ用レスポンシブCSSを適用"""
    bg = theme["bg"]
    sidebar_bg = theme["sidebar_bg"]
    card_bg = theme["card_bg"]
    text = theme["text"]
    sub_text = theme["sub_text"]
    border = theme["border"]
    table_border = theme["table_border"]
    row_hover = theme["row_hover"]
    header_grad = theme["header_grad"]
    is_dark = theme["is_dark"]

    sticky_css = ""
    if sticky_horse_col:
        sticky_css = f"""
        table.shutuba-custom td.sticky-col {{
            position: sticky;
            left: 0;
            z-index: 2;
            background: {card_bg};
            box-shadow: 2px 0 4px rgba(0,0,0,0.08);
        }}
        table.shutuba-custom tr:hover td.sticky-col {{
            background: {row_hover};
        }}
        """

    dark_overrides = ""
    if is_dark:
        dark_overrides = f"""
        .stMarkdown, .stText, p, span, label, h1, h2, h3, h4, h5, h6 {{
            color: {text};
        }}
        div[data-baseweb="select"] > div {{
            background-color: {bg} !important;
            color: {text} !important;
            border-color: {border} !important;
        }}
        input {{
            color: {text} !important;
            background-color: {bg} !important;
        }}
        div[data-testid="stExpander"] {{
            background-color: {card_bg} !important;
            border-color: {border} !important;
        }}
        button[kind="secondary"] {{
            background-color: {card_bg} !important;
            color: {text} !important;
            border-color: {border} !important;
        }}
        """

    css = f"""
    <style>
    .stApp {{
        background-color: {bg} !important;
        color: {text} !important;
    }}
    header[data-testid="stHeader"] {{
        background-color: {bg} !important;
    }}
    section[data-testid="stSidebar"] {{
        background-color: {sidebar_bg} !important;
        border-right: 1px solid {border} !important;
    }}
    {dark_overrides}
    .main-header {{
        background: {header_grad};
        color: white;
        padding: 1.0rem 1.4rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.18);
    }}
    .main-header h1 {{
        color: white !important;
        font-size: 1.45rem !important;
        margin: 0 0 0.25rem 0 !important;
        font-weight: 800 !important;
    }}
    .main-header p {{
        color: #e2e8f0 !important;
        font-size: 0.85rem !important;
        margin: 0 !important;
    }}
    .race-banner {{
        background: {card_bg};
        border: 1px solid {border};
        border-left: 6px solid #3b82f6;
        border-radius: 10px;
        padding: 0.85rem 1.1rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
    }}
    .status-pill {{
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 3px 9px;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 600;
        margin-right: 5px;
        margin-bottom: 5px;
        text-decoration: none !important;
    }}
    .status-ok {{
        background: #dcfce7;
        color: #166534 !important;
        border: 1px solid #86efac;
    }}
    .status-ng {{
        background: #fef3c7;
        color: #92400e !important;
        border: 1px solid #fde68a;
    }}
    .top-card {{
        background: {card_bg};
        border: 1px solid {border};
        border-radius: 10px;
        padding: 0.8rem 0.95rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        height: 100%;
        margin-bottom: 0.5rem;
    }}
    .shutuba-table-wrap {{
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        border: 1px solid {border};
        border-radius: 10px;
        background: {card_bg};
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}
    table.shutuba-custom {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.85rem;
        white-space: nowrap;
        color: {text};
    }}
    table.shutuba-custom th {{
        background: #1e293b;
        color: #ffffff !important;
        padding: 7px 9px;
        text-align: center;
        font-weight: 700;
        border: 1px solid #334155;
    }}
    table.shutuba-custom td {{
        padding: 6px 8px;
        border: 1px solid {table_border};
        text-align: center;
        vertical-align: middle;
        background: {card_bg};
        color: {text};
    }}
    table.shutuba-custom tr:hover td {{
        background-color: {row_hover};
    }}
    {sticky_css}
    .pt-badge {{
        display: inline-block;
        min-width: 32px;
        padding: 2px 7px;
        border-radius: 6px;
        font-weight: 800;
        font-size: 0.84rem;
        text-align: center;
    }}
    .raw-sub {{
        display: block;
        font-size: 0.71rem;
        color: {sub_text};
        margin-top: 2px;
    }}
    .waku-box {{
        display: inline-block;
        width: 23px;
        height: 23px;
        line-height: 21px;
        border-radius: 4px;
        font-weight: 800;
        text-align: center;
        font-size: 0.8rem;
    }}
    /* スマホ画面向けレスポンシブ最適化 */
    @media (max-width: 768px) {{
        .block-container {{
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
            padding-top: 1.5rem !important;
        }}
        .main-header {{
            padding: 0.75rem 1rem;
        }}
        .main-header h1 {{
            font-size: 1.15rem !important;
        }}
        .main-header p {{
            font-size: 0.75rem !important;
        }}
        table.shutuba-custom {{
            font-size: 0.78rem;
        }}
        table.shutuba-custom th, table.shutuba-custom td {{
            padding: 5px 6px;
        }}
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def format_raw_value(col_val: str, val: Any, is_low_umax: bool = False) -> str:
    if val is None or pd.isna(val):
        return "-"
    if col_val == "着順予想_値":
        return f"{int(val)}位予想"
    if col_val in ("オリジンAI_値", "ウェーブAI_値"):
        return f"{float(val):.1f}"
    if is_low_umax:
        return f"{int(round(float(val)))} (≤45)"
    return f"{int(round(float(val)))}"


def render_shutuba_html_table(
    df: pd.DataFrame, theme: Dict[str, Any], show_raw: bool = True
) -> str:
    """ポイントと元数値を色分けした見やすいHTMLテーブルを生成"""
    text_col = theme["text"]
    sub_col = theme["sub_text"]
    muted_col = theme["muted_text"]
    sub_bg = theme["sub_col_bg"]
    is_dark = theme["is_dark"]

    headers_html = (
        "<thead>"
        "<tr>"
        '<th rowspan="2">予想<br>順位</th>'
        '<th rowspan="2">枠</th>'
        '<th rowspan="2">馬番</th>'
        '<th rowspan="2" style="text-align:left;">馬名</th>'
        '<th rowspan="2">性齢<br>斤量</th>'
        '<th rowspan="2" style="text-align:left;">騎手</th>'
        '<th rowspan="2">単勝<br>オッズ</th>'
        '<th rowspan="2">人気</th>'
        '<th rowspan="2" style="background:#991b1b;font-size:0.95rem;">合計<br>PT</th>'
        '<th colspan="4" style="background:#1d4ed8;">② UMA-X 偏差値 (≤45は0pt)</th>'
        '<th colspan="1" style="background:#b45309;">② 競馬ラボ</th>'
        '<th colspan="2" style="background:#047857;">③ 無料競馬AI</th>'
        '<th colspan="1" style="background:#6d28d9;">④ keiba-ai</th>'
        '<th rowspan="2" style="background:#334155;">UMA<br>小計</th>'
        '<th rowspan="2" style="background:#334155;">AI<br>小計</th>'
        "</tr>"
        "<tr>"
        '<th style="background:#2563eb;">総合</th>'
        '<th style="background:#2563eb;">SP</th>'
        '<th style="background:#2563eb;">AG</th>'
        '<th style="background:#2563eb;">実績</th>'
        '<th style="background:#d97706;">Ω指数</th>'
        '<th style="background:#059669;">オリジン</th>'
        '<th style="background:#059669;">ウェーブ</th>'
        '<th style="background:#7c3aed;">着順予想</th>'
        "</tr>"
        "</thead>"
    )

    rows_html = []
    for _, row in df.iterrows():
        rank = int(row["予想順位"])
        waku = int(row["枠番"])
        umaban = int(row["馬番"])
        hname = row["馬名"]
        is_cancel = bool(row.get("取消", False))
        sex_age = row.get("性齢", "")
        kinryo = row.get("斤量", "")
        jockey = row.get("騎手", "")
        odds = row.get("単勝オッズ")
        ninki = row.get("人気")
        total_pt = int(row["合計_pt"])
        uma_sub = int(row["UMA小計_pt"])
        ai_sub = int(row["AI小計_pt"])

        # 順位メダル
        if is_cancel:
            rank_disp = '<span style="color:#ef4444;font-weight:bold;">取消</span>'
        elif rank == 1:
            c1 = "#fbbf24" if is_dark else "#b45309"
            rank_disp = f'<span style="font-size:1.0rem;font-weight:900;color:{c1};">🥇 1位</span>'
        elif rank == 2:
            c2 = "#e2e8f0" if is_dark else "#475569"
            rank_disp = f'<span style="font-size:0.95rem;font-weight:800;color:{c2};">🥈 2位</span>'
        elif rank == 3:
            c3 = "#fdba74" if is_dark else "#9a3412"
            rank_disp = f'<span style="font-size:0.95rem;font-weight:800;color:{c3};">🥉 3位</span>'
        elif rank <= 6 and total_pt > 0:
            rank_disp = f'<span style="font-weight:700;color:{text_col};">{rank}位</span>'
        else:
            rank_disp = f'<span style="color:{muted_col};">{rank}位</span>'

        # 枠番スタイル
        w_bg, w_fg, w_bd = WAKU_STYLE.get(waku, ("#f1f5f9", "#1e293b", "#cbd5e1"))
        waku_html = (
            f'<span class="waku-box" style="background:{w_bg};color:{w_fg};border:1px solid {w_bd};">'
            f"{waku if waku > 0 else '-'}</span>"
        )

        odds_str = f"{odds:.1f}" if (odds is not None and not pd.isna(odds)) else "---"
        ninki_str = f"{int(ninki)}人気" if (ninki is not None and not pd.isna(ninki)) else "-"
        if ninki is not None and not pd.isna(ninki) and int(ninki) <= 3:
            n_col = "#f87171" if is_dark else "#dc2626"
            ninki_str = f'<strong style="color:{n_col};">{ninki_str}</strong>'

        # 合計PTセルの強調
        if total_pt >= 35:
            tot_bg, tot_fg = "#991b1b", "#ffffff"
        elif total_pt >= 20:
            tot_bg, tot_fg = "#dc2626", "#ffffff"
        elif total_pt >= 10:
            tot_bg = "#7f1d1d" if is_dark else "#fee2e2"
            tot_fg = "#fecaca" if is_dark else "#991b1b"
        elif total_pt > 0:
            tot_bg = "#334155" if is_dark else "#f1f5f9"
            tot_fg = "#f8fafc" if is_dark else "#0f172a"
        else:
            tot_bg = "transparent"
            tot_fg = muted_col

        total_html = (
            f'<span style="display:inline-block;min-width:42px;padding:3px 7px;border-radius:6px;'
            f'background:{tot_bg};color:{tot_fg};font-weight:900;font-size:1.0rem;">{total_pt}</span>'
        )

        # 各8項目のセル
        item_cells = []
        for item in ITEM_META:
            pt = int(row[item["col_pt"]])
            raw_v = row[item["col_val"]]
            is_umax = item["cat"] == "UMA-X"
            is_low_umax = (
                is_umax
                and raw_v is not None
                and not pd.isna(raw_v)
                and float(raw_v) <= 45.0
            )
            bg, fg = PT_STYLE.get(pt, ("transparent", muted_col))
            if pt > 0:
                pt_span = f'<span class="pt-badge" style="background:{bg};color:{fg};">+{pt}</span>'
            else:
                pt_span = f'<span style="color:{muted_col};font-weight:600;">0</span>'

            if show_raw:
                raw_txt = format_raw_value(item["col_val"], raw_v, is_low_umax=is_low_umax)
                if item["col_val"] == "着順予想_値" and row.get("着順予想_指数"):
                    raw_txt += f" [{row.get('着順予想_指数').split('(')[0]}]"
                low_col = "#f87171" if is_dark else "#ef4444"
                sub_style = f"color:{low_col};" if is_low_umax else ""
                cell_inner = f'{pt_span}<span class="raw-sub" style="{sub_style}">({raw_txt})</span>'
            else:
                cell_inner = pt_span

            item_cells.append(f"<td>{cell_inner}</td>")

        uma_col = "#60a5fa" if is_dark else "#1d4ed8"
        ai_col = "#34d399" if is_dark else "#047857"
        row_style = "opacity:0.45;" if is_cancel else ""
        tr_html = (
            f'<tr style="{row_style}">'
            f"<td>{rank_disp}</td>"
            f"<td>{waku_html}</td>"
            f'<td style="font-weight:800;font-size:0.95rem;">{umaban}</td>'
            f'<td class="sticky-col" style="text-align:left;font-weight:700;color:{text_col};">{hname}</td>'
            f'<td style="font-size:0.78rem;color:{sub_col};">{sex_age}<br>{kinryo}</td>'
            f'<td style="text-align:left;font-size:0.83rem;color:{sub_col};">{jockey}</td>'
            f'<td style="font-weight:700;">{odds_str}</td>'
            f'<td style="font-size:0.79rem;">{ninki_str}</td>'
            f"<td>{total_html}</td>"
            f"{''.join(item_cells)}"
            f'<td style="font-weight:700;color:{uma_col};background:{sub_bg};">{uma_sub}</td>'
            f'<td style="font-weight:700;color:{ai_col};background:{sub_bg};">{ai_sub}</td>'
            f"</tr>"
        )
        rows_html.append(tr_html)

    return f'<div class="shutuba-table-wrap"><table class="shutuba-custom">{headers_html}<tbody>{"".join(rows_html)}</tbody></table></div>'


def _apply_chart_theme(chart: alt.Chart, theme: Dict[str, Any]) -> alt.Chart:
    text_col = theme["text"]
    grid_col = theme["table_border"]
    card_bg = theme["card_bg"]
    return (
        chart.configure(background=card_bg)
        .configure_axis(
            labelColor=text_col,
            titleColor=text_col,
            gridColor=grid_col,
            domainColor=grid_col,
        )
        .configure_legend(
            labelColor=text_col,
            titleColor=text_col,
        )
        .configure_view(stroke=grid_col)
    )


def build_stacked_bar_chart(df: pd.DataFrame, theme: Dict[str, Any]) -> alt.Chart:
    """⑥ 各項目のポイント付与状況を積み上げ横棒グラフで可視化"""
    active_df = df[df["取消"] == False].copy() if "取消" in df.columns else df.copy()
    active_df["馬ラベル"] = active_df.apply(
        lambda r: f"{int(r['馬番']):02d}番 {r['馬名']} ({int(r['合計_pt'])}pt)", axis=1
    )
    horse_order = active_df.sort_values(by=["合計_pt", "馬番"], ascending=[False, True])["馬ラベル"].tolist()

    records = []
    for _, row in active_df.iterrows():
        for idx, item in enumerate(ITEM_META):
            pt = int(row[item["col_pt"]])
            raw_v = row[item["col_val"]]
            records.append(
                {
                    "馬ラベル": row["馬ラベル"],
                    "馬番": int(row["馬番"]),
                    "馬名": row["馬名"],
                    "合計_pt": int(row["合計_pt"]),
                    "項目": item["label"],
                    "項目順": idx,
                    "カテゴリ": item["cat"],
                    "獲得ポイント": pt,
                    "元数値": format_raw_value(item["col_val"], raw_v),
                }
            )

    long_df = pd.DataFrame(records)
    domain_labels = [it["label"] for it in ITEM_META]
    range_colors = [it["color"] for it in ITEM_META]

    chart = (
        alt.Chart(long_df)
        .mark_bar(cornerRadiusEnd=3, height=22)
        .encode(
            y=alt.Y("馬ラベル:N", sort=horse_order, title="出走馬（合計ポイント順）", axis=alt.Axis(labelLimit=260)),
            x=alt.X("sum(獲得ポイント):Q", title="合計獲得ポイント (最大80pt)"),
            color=alt.Color(
                "項目:N",
                scale=alt.Scale(domain=domain_labels, range=range_colors),
                legend=alt.Legend(orient="top", title="評価項目 (8項目)"),
            ),
            order=alt.Order("項目順:Q", sort="ascending"),
            tooltip=[
                alt.Tooltip("馬番:Q", title="馬番"),
                alt.Tooltip("馬名:N", title="馬名"),
                alt.Tooltip("項目:N", title="評価項目"),
                alt.Tooltip("獲得ポイント:Q", title="獲得PT"),
                alt.Tooltip("元数値:N", title="元の指数・予想値"),
                alt.Tooltip("合計_pt:Q", title="合計PT"),
            ],
        )
        .properties(height=max(320, len(active_df) * 34))
    )
    return _apply_chart_theme(chart, theme)


def build_heatmap_chart(df: pd.DataFrame, theme: Dict[str, Any]) -> alt.Chart:
    """⑥ 出走馬×8項目のポイント付与マトリクス（ヒートマップ）"""
    active_df = df[df["取消"] == False].copy() if "取消" in df.columns else df.copy()
    active_df["馬ラベル"] = active_df.apply(
        lambda r: f"{int(r['馬番']):02d}番 {r['馬名']} ({int(r['合計_pt'])}pt)", axis=1
    )
    horse_order = active_df.sort_values(by=["合計_pt", "馬番"], ascending=[False, True])["馬ラベル"].tolist()
    item_order = [it["short"] for it in ITEM_META]

    records = []
    for _, row in active_df.iterrows():
        for item in ITEM_META:
            pt = int(row[item["col_pt"]])
            raw_v = row[item["col_val"]]
            raw_str = format_raw_value(item["col_val"], raw_v)
            disp_str = f"{pt}pt ({raw_str})" if pt > 0 else f"- ({raw_str})"
            records.append(
                {
                    "馬ラベル": row["馬ラベル"],
                    "馬名": row["馬名"],
                    "項目": item["short"],
                    "項目フル": item["label"],
                    "ポイント": pt,
                    "元数値": raw_str,
                    "セル表示": disp_str,
                }
            )

    hm_df = pd.DataFrame(records)
    zero_bg = "#1e293b" if theme["is_dark"] else "#f8fafc"
    zero_fg = "#cbd5e1" if theme["is_dark"] else "#1e293b"

    base = alt.Chart(hm_df).encode(
        x=alt.X("項目:N", sort=item_order, title="評価項目", axis=alt.Axis(labelAngle=0, orient="top")),
        y=alt.Y("馬ラベル:N", sort=horse_order, title="出走馬（合計ポイント順）", axis=alt.Axis(labelLimit=260)),
    )

    rect = base.mark_rect(stroke=theme["table_border"], strokeWidth=1).encode(
        color=alt.Color(
            "ポイント:Q",
            scale=alt.Scale(
                domain=[0, 1, 2, 3, 4, 6, 10],
                range=[zero_bg, "#e0f2fe", "#bae6fd", "#7dd3fc", "#fde68a", "#fdba74", "#f87171"],
            ),
            legend=alt.Legend(title="獲得PT"),
        ),
        tooltip=[
            alt.Tooltip("馬名:N", title="馬名"),
            alt.Tooltip("項目フル:N", title="項目"),
            alt.Tooltip("ポイント:Q", title="獲得PT"),
            alt.Tooltip("元数値:N", title="元の指数・予想値"),
        ],
    )

    text = base.mark_text(fontWeight="bold", fontSize=11).encode(
        text=alt.Text("セル表示:N"),
        color=alt.condition(alt.datum["ポイント"] > 0, alt.value("#0f172a"), alt.value(zero_fg)),
    )

    return _apply_chart_theme((rect + text).properties(height=max(340, len(active_df) * 36)), theme)


def build_value_scatter_chart(df: pd.DataFrame, theme: Dict[str, Any]) -> Optional[alt.Chart]:
    """人気（オッズ）× 合計ポイントの妙味分析チャート"""
    plot_df = df.dropna(subset=["人気"]).copy()
    if plot_df.empty:
        return None
    plot_df["人気"] = plot_df["人気"].astype(int)
    plot_df["ラベル"] = plot_df.apply(lambda r: f"{int(r['馬番'])}:{r['馬名']}", axis=1)

    pts = (
        alt.Chart(plot_df)
        .mark_circle(size=220, opacity=0.88, stroke=theme["text"], strokeWidth=1)
        .encode(
            x=alt.X("人気:Q", title="単勝人気 (左ほど上位人気)", scale=alt.Scale(zero=False)),
            y=alt.Y("合計_pt:Q", title="合計獲得ポイント (pt)"),
            color=alt.Color(
                "合計_pt:Q",
                scale=alt.Scale(scheme="redyellowblue", reverse=True),
                legend=alt.Legend(title="合計PT"),
            ),
            size=alt.Size("獲得項目数:Q", scale=alt.Scale(range=[120, 420]), legend=alt.Legend(title="獲得項目数")),
            tooltip=[
                alt.Tooltip("予想順位:Q", title="予想順位"),
                alt.Tooltip("馬番:Q", title="馬番"),
                alt.Tooltip("馬名:N", title="馬名"),
                alt.Tooltip("人気:Q", title="単勝人気"),
                alt.Tooltip("単勝オッズ:Q", title="単勝オッズ"),
                alt.Tooltip("合計_pt:Q", title="合計PT"),
                alt.Tooltip("UMA小計_pt:Q", title="UMA-X小計PT"),
                alt.Tooltip("Ω指数_pt:Q", title="Ω指数PT"),
                alt.Tooltip("AI小計_pt:Q", title="AI小計PT"),
            ],
        )
    )

    labels = (
        alt.Chart(plot_df)
        .mark_text(align="left", dx=10, dy=-4, fontSize=11, fontWeight="bold", color=theme["text"])
        .encode(
            x="人気:Q",
            y="合計_pt:Q",
            text="ラベル:N",
        )
    )

    return _apply_chart_theme((pts + labels).properties(height=380), theme)


def export_excel_bytes(df: pd.DataFrame, meta: Dict[str, Any]) -> bytes:
    output = io.BytesIO()
    export_cols = [
        "予想順位",
        "枠番",
        "馬番",
        "馬名",
        "性齢",
        "斤量",
        "騎手",
        "厩舎",
        "単勝オッズ",
        "人気",
        "合計_pt",
        "UMA小計_pt",
        "AI小計_pt",
        "獲得項目数",
        "UMA総合_pt",
        "UMA総合_値",
        "UMASP_pt",
        "UMASP_値",
        "UMAAG_pt",
        "UMAAG_値",
        "UMA実績_pt",
        "UMA実績_値",
        "Ω指数_pt",
        "Ω指数_値",
        "オリジンAI_pt",
        "オリジンAI_値",
        "ウェーブAI_pt",
        "ウェーブAI_値",
        "着順予想_pt",
        "着順予想_値",
        "着順予想_指数",
    ]
    avail_cols = [c for c in export_cols if c in df.columns]
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df[avail_cols].to_excel(writer, index=False, sheet_name="ポイント出馬表")
    return output.getvalue()


def resolve_current_theme(cfg: Dict[str, Any]) -> Dict[str, Any]:
    tname = cfg.get("theme_name", "☀️ ライト（標準）")
    if tname in THEME_PRESETS:
        return THEME_PRESETS[tname]
    # カスタムカラー
    bg = cfg.get("custom_bg", "#1e293b")
    card = cfg.get("custom_card", "#334155")
    txt = cfg.get("custom_text", "#f8fafc")
    # 簡易輝度判定
    try:
        r_v = int(bg.lstrip("#")[0:2], 16)
        g_v = int(bg.lstrip("#")[2:4], 16)
        b_v = int(bg.lstrip("#")[4:6], 16)
        is_dark = (r_v * 0.299 + g_v * 0.587 + b_v * 0.114) < 140
    except Exception:
        is_dark = True
    return {
        "is_dark": is_dark,
        "bg": bg,
        "sidebar_bg": card,
        "card_bg": card,
        "text": txt,
        "sub_text": "#cbd5e1" if is_dark else "#475569",
        "muted_text": "#64748b" if is_dark else "#94a3b8",
        "border": "#475569" if is_dark else "#cbd5e1",
        "table_border": "#475569" if is_dark else "#e2e8f0",
        "row_hover": "#475569" if is_dark else "#f1f5f9",
        "sub_col_bg": bg,
        "tag_bg": bg,
        "header_grad": "linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%)",
    }


def main() -> None:
    cfg = load_user_config()

    # ------------------------------------------------------------------
    # サイドバー: レース選択 & 画面テーマ & スマホ接続QR
    # ------------------------------------------------------------------
    with st.sidebar:
        st.header("🔍 レース選択")

        select_mode = st.radio(
            "選択方法",
            ["📅 開催日・競馬場から選択", "🔗 netkeiba URL / race_id 入力"],
            index=0,
        )

        selected_race_id = ""
        selected_kaisai_date = ""

        if select_mode == "📅 開催日・競馬場から選択":
            jst = datetime.timezone(datetime.timedelta(hours=9))
            default_date = datetime.datetime.now(jst).date()
            picked_date = st.date_input("開催日を選択", value=default_date)
            kaisai_date_str = picked_date.strftime("%Y%m%d")
            selected_kaisai_date = kaisai_date_str

            with st.spinner("開催レース一覧を取得中..."):
                races_raw = cached_get_races_for_date(kaisai_date_str, cfg.get("netkeiba_cookie", ""))

            if not races_raw:
                st.warning(
                    f"{picked_date.strftime('%Y年%m月%d日')} の中央競馬(JRA)開催データが見つかりません。土・日などの開催日を選択してください。"
                )
            else:
                venues = []
                for r in races_raw:
                    if r["venue_name"] not in venues:
                        venues.append(r["venue_name"])

                selected_venue = st.selectbox("競馬場を選択", venues)
                venue_races = [r for r in races_raw if r["venue_name"] == selected_venue]

                race_options = {}
                default_idx = 0
                for idx, r in enumerate(venue_races):
                    label = f"{r['race_num']}R {r['race_name']} ({r['start_time']} {r['course_info']})".strip()
                    race_options[label] = r["race_id"]
                    if r["race_num"] == 11:
                        default_idx = idx

                selected_label = st.selectbox(
                    "レースを選択",
                    list(race_options.keys()),
                    index=default_idx,
                )
                selected_race_id = race_options[selected_label]

        else:
            raw_input = st.text_input(
                "netkeiba 出馬表URL または 12桁 race_id",
                placeholder="例: https://race.netkeiba.com/race/shutuba.html?race_id=202605040811",
            )
            m_rid = re.search(r"(\d{12})", raw_input)
            if m_rid:
                selected_race_id = m_rid.group(1)
            elif raw_input.strip():
                st.error("12桁の race_id が見つかりません。URLまたは12桁の数字を入力してください。")

        fetch_clicked = st.button(
            "🚀 予想データを取得・集計する",
            type="primary",
            use_container_width=True,
            disabled=(not selected_race_id),
        )

        if st.button("🔄 キャッシュをクリアして再取得", use_container_width=True):
            st.cache_data.clear()
            if selected_race_id:
                st.session_state["current_race_id"] = selected_race_id
                st.session_state["current_kaisai_date"] = selected_kaisai_date
            st.rerun()

        if selected_kaisai_date and st.button(
            "📦 この開催日の全レース指数を一括保存 (クラウド用)",
            use_container_width=True,
            help="UMA-X・競馬ラボ・無料競馬AIの指数を選択日全レース分まとめて race_cache.json に保存します。",
        ):
            from prefetch_weekend import prefetch_dates

            with st.spinner(f"{selected_kaisai_date} の全レース指数を一括取得・保存中..."):
                cnt = prefetch_dates([selected_kaisai_date])
                st.cache_data.clear()
            st.success(f"全レース一括保存完了！（累計 {cnt} レース）")

        st.divider()

        # 🎨 画面テーマ・背景色設定
        st.subheader("🎨 背景色・テーマ設定")
        theme_choices = list(THEME_PRESETS.keys()) + ["🎛️ カスタムカラー"]
        saved_theme = cfg.get("theme_name", "☀️ ライト（標準）")
        t_idx = theme_choices.index(saved_theme) if saved_theme in theme_choices else 0

        picked_theme_name = st.selectbox("カラーテーマ", theme_choices, index=t_idx)
        cfg["theme_name"] = picked_theme_name

        if picked_theme_name == "🎛️ カスタムカラー":
            c_col1, c_col2, c_col3 = st.columns(3)
            with c_col1:
                cfg["custom_bg"] = st.color_picker("背景色", value=cfg.get("custom_bg", "#1e293b"))
            with c_col2:
                cfg["custom_card"] = st.color_picker("表・カード", value=cfg.get("custom_card", "#334155"))
            with c_col3:
                cfg["custom_text"] = st.color_picker("文字色", value=cfg.get("custom_text", "#f8fafc"))

        sticky_col = st.checkbox(
            "スマホ横スクロール時に「馬名」列を固定",
            value=bool(cfg.get("sticky_horse_col", True)),
        )
        cfg["sticky_horse_col"] = sticky_col
        save_user_config(cfg)

        st.divider()

        # 📱 スマートフォン・他端末接続 (QRコード付き)
        with st.expander("📱 スマホ・他端末から使う", expanded=False):
            cloud_url = "https://keiba-predictor-3kuzt9et8q4ir44n97iyda.streamlit.app/"
            st.markdown(
                f"**☁️ 外出先（4G/5G・競馬場）専用クラウドURL**:\n"
                f"PCの電源がOFFでもスマホ単独で24時間使えます。\n\n"
                f"🔗 [{cloud_url}]({cloud_url})"
            )
            try:
                qr_cloud = make_qr_png_bytes(cloud_url)
                st.image(qr_cloud, caption="スマホカメラでスキャン (クラウド版)", width=180)
            except Exception:
                pass
            st.markdown("---")
            local_ip = get_local_ip()
            mobile_url = f"http://{local_ip}:8502"
            st.markdown(
                f"**🏠 自宅Wi-Fi接続用URL**:\n"
                f"🔗 `{mobile_url}`"
            )
            try:
                qr_bytes = make_qr_png_bytes(mobile_url)
                st.image(qr_bytes, caption=f"自宅Wi-Fi用QRコード ({mobile_url})", width=180)
            except Exception:
                pass

        with st.expander("📋 ポイント付与ルール確認", expanded=False):
            st.markdown(
                """
                - **配点（各項目共通）**:
                  - **1位**: `10pt` / **2位**: `6pt` / **3位**: `4pt`
                  - **4位**: `3pt` / **5位**: `2pt` / **6位**: `1pt`
                  - 同率順位は全員に同ポイントを付与し、次順位は頭数分スキップ
                - **集計対象（計8項目・最大80pt）**:
                  1. **UMA-X 総合** *(偏差値45以下は0pt)*
                  2. **UMA-X SP** *(偏差値45以下は0pt)*
                  3. **UMA-X AG** *(偏差値45以下は0pt)*
                  4. **UMA-X 実績** *(偏差値45以下は0pt)*
                  5. **競馬ラボ ウェブ新聞 Ω指数**
                  6. **無料競馬AI オリジンAI**
                  7. **無料競馬AI ウェーブAI**
                  8. **keiba-ai.jp 着順予想**
                """
            )

        with st.expander("🔐 ログイン・Cookie設定 (任意)", expanded=False):
            st.caption(
                "netkeiba.com・keibalab.jp は通常そのままで取得可能ですが、ログイン状態を明示的に反映したい場合は設定して保存できます。"
            )
            nk_id = st.text_input("netkeiba ログインID (メール)", value=cfg.get("netkeiba_id", ""))
            nk_pass = st.text_input("netkeiba パスワード", value=cfg.get("netkeiba_pass", ""), type="password")
            nk_cookie = st.text_input("netkeiba Cookie (任意)", value=cfg.get("netkeiba_cookie", ""))
            st.markdown("---")
            kl_email = st.text_input("競馬ラボ メールアドレス", value=cfg.get("keibalab_email", ""))
            kl_pass = st.text_input("競馬ラボ パスワード", value=cfg.get("keibalab_pass", ""), type="password")
            kl_cookie = st.text_input("競馬ラボ Cookie (任意)", value=cfg.get("keibalab_cookie", ""))

            if st.button("💾 認証設定を保存", use_container_width=True):
                cfg.update(
                    {
                        "netkeiba_id": nk_id,
                        "netkeiba_pass": nk_pass,
                        "netkeiba_cookie": nk_cookie,
                        "keibalab_email": kl_email,
                        "keibalab_pass": kl_pass,
                        "keibalab_cookie": kl_cookie,
                    }
                )
                save_user_config(cfg)
                st.cache_data.clear()
                st.success("認証設定を保存しました！")

    # テーマCSSを適用
    current_theme = resolve_current_theme(cfg)
    inject_theme_css(current_theme, sticky_horse_col=sticky_col)

    # ヘッダー
    st.markdown(
        '<div class="main-header">'
        "<h1>🏇 競馬予想 マルチ指数＆AI ポイント総合集計アプリ</h1>"
        "<p>netkeiba出馬表 × UMA-X偏差値(4項目) × 競馬ラボΩ指数 × 無料競馬AI(2項目) × keiba-ai着順予想 の計8項目(最大80pt)を自動集計・可視化</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    # セッション状態の初期化・更新
    if fetch_clicked and selected_race_id:
        st.session_state["current_race_id"] = selected_race_id
        st.session_state["current_kaisai_date"] = selected_kaisai_date

    if "current_race_id" not in st.session_state and selected_race_id:
        st.session_state["current_race_id"] = selected_race_id
        st.session_state["current_kaisai_date"] = selected_kaisai_date

    active_race_id = st.session_state.get("current_race_id", "")
    active_kaisai_date = st.session_state.get("current_kaisai_date", "")

    if not active_race_id:
        st.info("👈 左側のサイドバーから開催日・競馬場・レースを選択して「予想データを取得・集計する」を押してください。")
        return

    # ------------------------------------------------------------------
    # データ取得と集計実行
    # ------------------------------------------------------------------
    with st.spinner("5サイト (netkeiba / UMA-X / 競馬ラボ / 無料競馬AI / keiba-ai.jp) からデータを取得・集計中..."):
        meta_dict, df, statuses = cached_analyze_race(
            active_race_id,
            active_kaisai_date,
            cfg.get("netkeiba_cookie", ""),
            cfg.get("keibalab_cookie", ""),
            cfg.get("netkeiba_id", ""),
            cfg.get("netkeiba_pass", ""),
            cfg.get("keibalab_email", ""),
            cfg.get("keibalab_pass", ""),
        )

    if not meta_dict or df.empty:
        st.error("出馬表データの取得に失敗しました。レースIDまたは通信状況を確認してください。")
        for s in statuses:
            st.write(f"- **{s['site_name']}**: {s['message']}")
        return

    # ------------------------------------------------------------------
    # レース情報バナー & 5サイト取得ステータス表示
    # ------------------------------------------------------------------
    kd = meta_dict.get("kaisai_date", "")
    kd_fmt = f"{kd[0:4]}年{int(kd[4:6])}月{int(kd[6:8])}日" if len(kd) == 8 else kd

    pills_html = []
    for s in statuses:
        cls = "status-ok" if s["success"] else "status-ng"
        icon = "✅" if s["success"] else "⚠️"
        href = f'href="{s["url"]}" target="_blank"' if s.get("url") else ""
        pills_html.append(
            f'<a {href} class="status-pill {cls}" title="{s["message"]}">'
            f'{icon} {s["site_name"]}: {s["message"]} ↗</a>'
        )

    banner_html = (
        f'<div class="race-banner">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">'
        f"<div>"
        f'<span style="background:#1b6ca8;color:white;padding:3px 10px;border-radius:6px;font-weight:800;font-size:0.9rem;margin-right:8px;">'
        f"{meta_dict['venue_name']} {meta_dict['race_num']}R"
        f"</span>"
        f'<span style="font-size:1.35rem;font-weight:900;color:{current_theme["text"]};">'
        f"{meta_dict['race_name']}"
        f"</span>"
        f'<span style="color:{current_theme["sub_text"]};font-size:0.9rem;margin-left:10px;">'
        f"📅 {kd_fmt} ｜ ⏰ {meta_dict['start_time']}発走 ｜ 🏟️ {meta_dict['course_info']}"
        f"{'｜ 天候:' + meta_dict['weather'] if meta_dict.get('weather') else ''}"
        f"{'｜ 馬場:' + meta_dict['track_condition'] if meta_dict.get('track_condition') else ''}"
        f"</span>"
        f"</div>"
        f'<div style="font-size:0.78rem;color:{current_theme["muted_text"]};">race_id: {meta_dict["race_id"]}</div>'
        f"</div>"
        f'<div style="margin-top:10px;">'
        f"{''.join(pills_html)}"
        f"</div>"
        f"</div>"
    )
    st.markdown(banner_html, unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 上位注目馬ピックアップカード (Top 4)
    # ------------------------------------------------------------------
    active_horses = df[df["取消"] == False] if "取消" in df.columns else df
    top_horses = active_horses.head(4)
    if not top_horses.empty:
        cols_top = st.columns(len(top_horses))
        medals = ["🥇 予想1位 (◎本命候補)", "🥈 予想2位 (○対抗候補)", "🥉 予想3位 (▲単穴候補)", "🏅 予想4位 (△連下候補)"]
        border_colors = ["#ef4444", "#3b82f6", "#f59e0b", "#10b981"]

        for idx, (_, hrow) in enumerate(top_horses.iterrows()):
            with cols_top[idx]:
                waku = int(hrow["枠番"])
                w_bg, w_fg, w_bd = WAKU_STYLE.get(waku, ("#f1f5f9", "#1e293b", "#cbd5e1"))
                odds_v = hrow.get("単勝オッズ")
                ninki_v = hrow.get("人気")
                odds_txt = f"{odds_v:.1f}倍" if (odds_v is not None and not pd.isna(odds_v)) else "---"
                ninki_txt = f"{int(ninki_v)}番人気" if (ninki_v is not None and not pd.isna(ninki_v)) else "-"

                earned_tags = []
                pt_highlight_col = "#f87171" if current_theme["is_dark"] else "#b91c1c"
                for item in ITEM_META:
                    pt = int(hrow[item["col_pt"]])
                    if pt > 0:
                        earned_tags.append(
                            f'<span style="display:inline-block;background:{current_theme["tag_bg"]};'
                            f'border:1px solid {current_theme["border"]};color:{current_theme["text"]};'
                            f'border-radius:4px;padding:1px 5px;font-size:0.72rem;margin:2px;">'
                            f'{item["short"]}:<strong style="color:{pt_highlight_col};">+{pt}</strong></span>'
                        )

                tags_inner = (
                    "".join(earned_tags)
                    if earned_tags
                    else f'<span style="font-size:0.75rem;color:{current_theme["muted_text"]};">獲得ポイントなし</span>'
                )
                card_html = (
                    f'<div class="top-card" style="border-top: 4px solid {border_colors[idx]};">'
                    f'<div style="font-size:0.78rem;font-weight:700;color:{border_colors[idx]};margin-bottom:4px;">'
                    f"{medals[idx]}"
                    f"</div>"
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f"<div>"
                    f'<span class="waku-box" style="background:{w_bg};color:{w_fg};border:1px solid {w_bd};margin-right:4px;">{waku}</span>'
                    f'<span style="font-size:1.08rem;font-weight:900;color:{current_theme["text"]};">{int(hrow["馬番"])}番 {hrow["馬名"]}</span>'
                    f"</div>"
                    f'<div style="background:#991b1b;color:white;padding:3px 9px;border-radius:8px;font-weight:900;font-size:1.02rem;">'
                    f'{int(hrow["合計_pt"])} <span style="font-size:0.75rem;font-weight:normal;">pt</span>'
                    f"</div>"
                    f"</div>"
                    f'<div style="font-size:0.8rem;color:{current_theme["sub_text"]};margin:5px 0;">'
                    f'騎手: <strong>{hrow["騎手"]}</strong> ({hrow["斤量"]}) ｜ 単勝: <strong>{odds_txt}</strong> ({ninki_txt})'
                    f"</div>"
                    f'<div style="margin-top:4px;">{tags_inner}</div>'
                    f"</div>"
                )
                st.markdown(card_html, unsafe_allow_html=True)

    st.write("")

    # ------------------------------------------------------------------
    # ⑤ ソート機能付き ポイント出馬表
    # ------------------------------------------------------------------
    st.subheader("📊 ⑤ 項目別ポイント＆合計ポイント 出馬表")

    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([2.2, 2.2, 1.3, 1.3])
    with ctrl_col1:
        sort_option = st.selectbox(
            "並び順（ソート）",
            [
                "合計ポイント順（高い順）",
                "馬番順（1番〜）",
                "UMA-X 小計ポイント順",
                "競馬ラボ Ω指数ポイント順",
                "AI予想 小計ポイント順",
                "単勝人気順",
            ],
            index=0,
        )
    with ctrl_col2:
        disp_mode = st.radio(
            "セル表示モード",
            ["ポイント ＋ 元の指数・予想値", "ポイントのみシンプル表示"],
            index=0,
            horizontal=True,
        )

    # 並び替え適用
    display_df = df.copy()
    if sort_option == "合計ポイント順（高い順）":
        display_df = display_df.sort_values(by=["合計_pt", "獲得項目数", "馬番"], ascending=[False, False, True])
    elif sort_option == "馬番順（1番〜）":
        display_df = display_df.sort_values(by=["馬番"], ascending=True)
    elif sort_option == "UMA-X 小計ポイント順":
        display_df = display_df.sort_values(by=["UMA小計_pt", "合計_pt", "馬番"], ascending=[False, False, True])
    elif sort_option == "競馬ラボ Ω指数ポイント順":
        display_df = display_df.sort_values(by=["Ω指数_pt", "Ω指数_値", "合計_pt"], ascending=[False, False, False])
    elif sort_option == "AI予想 小計ポイント順":
        display_df = display_df.sort_values(by=["AI小計_pt", "合計_pt", "馬番"], ascending=[False, False, True])
    elif sort_option == "単勝人気順":
        display_df = display_df.sort_values(by=["人気", "馬番"], ascending=[True, True], na_position="last")

    # CSV / Excel ダウンロードボタン
    csv_bytes = display_df.to_csv(index=False).encode("utf-8-sig")
    file_prefix = f"{meta_dict['kaisai_date']}_{meta_dict['venue_name']}{meta_dict['race_num']}R_{meta_dict['race_name']}"
    with ctrl_col3:
        st.download_button(
            "📥 CSVダウンロード",
            data=csv_bytes,
            file_name=f"{file_prefix}_ポイント表.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with ctrl_col4:
        excel_bytes = export_excel_bytes(display_df, meta_dict)
        st.download_button(
            "📗 Excelダウンロード",
            data=excel_bytes,
            file_name=f"{file_prefix}_ポイント表.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    # カスタムカラー出馬表の表示
    show_raw_flag = disp_mode == "ポイント ＋ 元の指数・予想値"
    html_table = render_shutuba_html_table(display_df, theme=current_theme, show_raw=show_raw_flag)
    st.markdown(html_table, unsafe_allow_html=True)
    st.caption(
        "※ 各項目の上位1〜6位に **10, 6, 4, 3, 2, 1 pt** を付与（同率順位は同ポイント付与・次順位スキップ）。"
        " **UMA-Xの4項目（総合・SP・AG・実績）は偏差値45以下の馬にはポイントを付与しません（0pt）**。"
    )

    st.divider()

    # ------------------------------------------------------------------
    # ⑥ 各項目のポイント付与状況の可視化
    # ------------------------------------------------------------------
    st.subheader("📈 ⑥ 各項目のポイント付与状況の可視化")

    tab_bar, tab_hm, tab_scatter, tab_raw = st.tabs(
        [
            "📊 項目別 積み上げポイントグラフ",
            "🟧 出走馬×8項目 ポイントヒートマップ",
            "💎 単勝人気 × 合計ポイント 妙味分析",
            "🔢 取得生データ・ポイント一覧表",
        ]
    )

    with tab_bar:
        st.markdown("##### 馬別・評価項目別 ポイント内訳（積み上げ横棒グラフ）")
        st.caption("棒にマウスカーソル（スマホはタップ）を合わせると、各項目の獲得ポイントと元の指数値が確認できます。")
        bar_chart = build_stacked_bar_chart(df, theme=current_theme)
        st.altair_chart(bar_chart, use_container_width=True)

    with tab_hm:
        st.markdown("##### 出走馬 × 8評価項目 ポイント付与マトリクス（ヒートマップ）")
        st.caption("どの馬がどの項目（スピード・上がり・実績・Ω指数・各AI）で何ポイント獲得したかを一覧比較できます。")
        hm_chart = build_heatmap_chart(df, theme=current_theme)
        st.altair_chart(hm_chart, use_container_width=True)

    with tab_scatter:
        st.markdown("##### 単勝人気 × 合計獲得ポイント 散布図（妙味・穴馬発見）")
        st.caption(
            "右上にある馬ほど「人気薄（高配当）でありながら指数・AIの合計ポイントが高い妙味馬（穴馬候補）」です。"
        )
        scatter_chart = build_value_scatter_chart(df, theme=current_theme)
        if scatter_chart is not None:
            st.altair_chart(scatter_chart, use_container_width=True)
        else:
            st.info("単勝オッズ・人気データがまだ発表されていないため散布図は表示できません。")

    with tab_raw:
        st.markdown("##### 取得元数値（生データ）＆ポイント一覧（ソート・検索対応）")
        raw_cols = [
            "予想順位",
            "枠番",
            "馬番",
            "馬名",
            "騎手",
            "単勝オッズ",
            "人気",
            "合計_pt",
            "UMA総合_値",
            "UMA総合_pt",
            "UMASP_値",
            "UMASP_pt",
            "UMAAG_値",
            "UMAAG_pt",
            "UMA実績_値",
            "UMA実績_pt",
            "Ω指数_値",
            "Ω指数_pt",
            "オリジンAI_値",
            "オリジンAI_pt",
            "ウェーブAI_値",
            "ウェーブAI_pt",
            "着順予想_値",
            "着順予想_指数",
            "着順予想_pt",
        ]
        avail_raw = [c for c in raw_cols if c in display_df.columns]
        st.dataframe(display_df[avail_raw], use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
