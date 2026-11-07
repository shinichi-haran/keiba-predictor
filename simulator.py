"""
ウイニングポスト風 レースシミュレーション＆能力パラメータ連動モジュール
- 取得データ（8項目＋合計PT＋人気/オッズ）と4大能力パラメータ（スピード・瞬発力・スタミナ・勝負根性）の柔軟な連動設定
- 視点切替（ダイナミックTVカメラ / サイドビュー / 2Dコース全体俯瞰）
- デザイン切替（ウイニングポスト風 / JRA TV中継風 / レトロアーケード風）
- HTML5 Canvas インタラクティブ実況ビューア & モンテカルロ100回シミュレーション集計
"""

from __future__ import annotations

import json
import math
import random
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# ---------------------------------------------------------------------------
# 1. 取得データ項目カタログ（後で自由に追加・変更可能な定義）
# ---------------------------------------------------------------------------
SOURCE_METRICS: List[Dict[str, Any]] = [
    {
        "key": "UMA総合",
        "label": "UMA-X 総合偏差値",
        "col_val": "UMA総合_値",
        "col_pt": "UMA総合_pt",
        "mode": "deviation",  # 平均50, 標準偏差10程度
    },
    {
        "key": "UMASP",
        "label": "UMA-X SP(スピード)偏差値",
        "col_val": "UMASP_値",
        "col_pt": "UMASP_pt",
        "mode": "deviation",
    },
    {
        "key": "UMAAG",
        "label": "UMA-X AG(上がり末脚)偏差値",
        "col_val": "UMAAG_値",
        "col_pt": "UMAAG_pt",
        "mode": "deviation",
    },
    {
        "key": "UMA実績",
        "label": "UMA-X 実績偏差値",
        "col_val": "UMA実績_値",
        "col_pt": "UMA実績_pt",
        "mode": "deviation",
    },
    {
        "key": "Ω指数",
        "label": "競馬ラボ Ω指数",
        "col_val": "Ω指数_値",
        "col_pt": "Ω指数_pt",
        "mode": "higher_better",
    },
    {
        "key": "オリジンAI",
        "label": "無料競馬AI オリジン指数",
        "col_val": "オリジンAI_値",
        "col_pt": "オリジンAI_pt",
        "mode": "higher_better",
    },
    {
        "key": "ウェーブAI",
        "label": "無料競馬AI ウェーブ指数",
        "col_val": "ウェーブAI_値",
        "col_pt": "ウェーブAI_pt",
        "mode": "higher_better",
    },
    {
        "key": "着順予想",
        "label": "keiba-ai 着順予想",
        "col_val": "着順予想_値",
        "col_pt": "着順予想_pt",
        "mode": "rank_lower_better",
    },
    {
        "key": "合計PT",
        "label": "8項目 合計獲得ポイント",
        "col_val": "合計_pt",
        "col_pt": "合計_pt",
        "mode": "total_pt",
    },
]

METRIC_KEY_TO_LABEL: Dict[str, str] = {m["key"]: m["label"] for m in SOURCE_METRICS}
METRIC_LABEL_TO_KEY: Dict[str, str] = {m["label"]: m["key"] for m in SOURCE_METRICS}

# 4大能力パラメータ定義
ABILITY_PARAMS: List[Dict[str, str]] = [
    {
        "id": "speed",
        "name": "⚡ スピード (道中巡航・先行力)",
        "short": "スピード",
        "desc": "基礎巡航速度と好位を取りに行く先行力に影響します。",
    },
    {
        "id": "accel",
        "name": "🔥 瞬発力・末脚 (直線の伸び・加速)",
        "short": "瞬発力",
        "desc": "第3〜4コーナーから最後の直線での末脚爆発力・上がり3Fの速さに影響します。",
    },
    {
        "id": "stamina",
        "name": "💪 スタミナ・持続力 (距離適性・粘り)",
        "short": "スタミナ",
        "desc": "ハイペースや長距離でのバテにくさ、トップスピードの持続時間に影響します。",
    },
    {
        "id": "guts",
        "name": "⚔️ 勝負根性・安定感 (競り合い・底力)",
        "short": "勝負根性",
        "desc": "ゴール前の叩き合いでの強さや、出遅れ・前詰まり等の不利を跳ね返す安定感に影響します。",
    },
]

# ---------------------------------------------------------------------------
# 2. 能力パラメータ連動プリセット定義（後からでも簡単に変更・拡張可能）
# ---------------------------------------------------------------------------
PARAM_MAPPING_PRESETS: Dict[str, Dict[str, Any]] = {
    "🏆 標準バランス（推奨：各指数の特性を適材適所で連動）": {
        "calc_source": "hybrid",  # "hybrid" (元数値+PT), "raw_only" (元数値のみ), "pt_only" (獲得PTのみ)
        "random_factor": 0.25,
        "weights": {
            "speed": {"UMASP": 45, "Ω指数": 35, "UMA総合": 20},
            "accel": {"UMAAG": 50, "ウェーブAI": 30, "オリジンAI": 20},
            "stamina": {"UMA実績": 40, "UMA総合": 30, "オリジンAI": 30},
            "guts": {"着順予想": 35, "合計PT": 45, "Ω指数": 20},
        },
    },
    "⚡ スピード＆Ω指数重視（時計・先行スピード優先）": {
        "calc_source": "hybrid",
        "random_factor": 0.20,
        "weights": {
            "speed": {"UMASP": 60, "Ω指数": 40},
            "accel": {"UMAAG": 40, "Ω指数": 40, "UMASP": 20},
            "stamina": {"UMA総合": 50, "UMA実績": 50},
            "guts": {"Ω指数": 50, "合計PT": 50},
        },
    },
    "🔥 直線末脚（UMA-X AG ＆ AI指数）重視": {
        "calc_source": "hybrid",
        "random_factor": 0.25,
        "weights": {
            "speed": {"UMASP": 40, "オリジンAI": 30, "ウェーブAI": 30},
            "accel": {"UMAAG": 65, "ウェーブAI": 35},
            "stamina": {"UMA総合": 40, "オリジンAI": 40, "UMA実績": 20},
            "guts": {"着順予想": 50, "ウェーブAI": 25, "オリジンAI": 25},
        },
    },
    "🤖 AI予想フル重視（オリジン・ウェーブ・keiba-ai中心）": {
        "calc_source": "hybrid",
        "random_factor": 0.25,
        "weights": {
            "speed": {"オリジンAI": 50, "ウェーブAI": 30, "UMASP": 20},
            "accel": {"ウェーブAI": 50, "着順予想": 30, "UMAAG": 20},
            "stamina": {"オリジンAI": 50, "着順予想": 50},
            "guts": {"着順予想": 50, "オリジンAI": 25, "ウェーブAI": 25},
        },
    },
    "📊 獲得ポイント直結モード（出馬表のポイント通りに能力化）": {
        "calc_source": "pt_only",
        "random_factor": 0.20,
        "weights": {
            "speed": {"UMASP": 40, "Ω指数": 40, "合計PT": 20},
            "accel": {"UMAAG": 40, "ウェーブAI": 30, "合計PT": 30},
            "stamina": {"UMA総合": 40, "UMA実績": 30, "オリジンAI": 30},
            "guts": {"合計PT": 60, "着順予想": 40},
        },
    },
}


def parse_course_details(meta_dict: Dict[str, Any]) -> Dict[str, Any]:
    """レースメタ情報から芝/ダート・距離・回り・馬場状態などを構造化"""
    c_info = str(meta_dict.get("course_info", ""))
    venue = str(meta_dict.get("venue_name", "東京"))
    weather = str(meta_dict.get("weather", "晴")) or "晴"
    cond = str(meta_dict.get("track_condition", "良")) or "良"

    surface = "ダート" if "ダ" in c_info else ("障害" if "障" in c_info else "芝")
    m_dist = re.search(r"(\d{3,4})\s*m", c_info)
    distance = int(m_dist.group(1)) if m_dist else 1600

    if "直線" in c_info:
        turn = "直線"
    elif "左" in c_info:
        turn = "左"
    elif "右" in c_info:
        turn = "右"
    else:
        # 競馬場からのデフォルト推定
        turn = "左" if venue in ("東京", "新潟", "中京") else "右"

    # 直線の長さ・坂の有無（競馬場特徴）
    straight_len = 400
    has_hill = False
    if venue == "東京":
        straight_len = 525
        has_hill = True
    elif venue == "新潟":
        straight_len = 1000 if turn == "直線" else (658 if "外" in c_info else 359)
        has_hill = False
    elif venue == "中山":
        straight_len = 310
        has_hill = True
    elif venue == "京都":
        straight_len = 404 if "外" in c_info else 328
        has_hill = False
    elif venue == "阪神":
        straight_len = 473 if "外" in c_info else 356
        has_hill = True
    elif venue == "中京":
        straight_len = 412
        has_hill = True
    elif venue in ("札幌", "函館", "福島", "小倉"):
        straight_len = 290
        has_hill = False

    return {
        "venue": venue,
        "surface": surface,
        "distance": distance,
        "turn": turn,
        "weather": weather,
        "condition": cond,
        "straight_len": straight_len,
        "has_hill": has_hill,
        "race_name": str(meta_dict.get("race_name", "特別レース")),
        "race_num": int(meta_dict.get("race_num", 11) or 11),
    }


def _normalize_series_to_score(df: pd.DataFrame, metric: Dict[str, Any], calc_source: str) -> pd.Series:
    """
    各指標を 35.0 〜 75.0 (基準50.0) の統一能力スケールに正規化する。
    欠損値がある場合はレース内の中央値(50.0)で安全に補完する。
    """
    n = len(df)
    if n == 0:
        return pd.Series(dtype=float)

    col_val = metric["col_val"]
    col_pt = metric["col_pt"]
    mode = metric["mode"]

    # 1. ポイントスコア (0〜10pt -> 44〜68、合計PTの場合は0〜80pt -> 42〜72)
    pt_series = pd.to_numeric(df.get(col_pt, pd.Series([0] * n, index=df.index)), errors="coerce").fillna(0.0)
    if mode == "total_pt":
        max_pt = max(float(pt_series.max()), 10.0)
        pt_score = 43.0 + (pt_series / max_pt) * 29.0
    else:
        pt_score = 44.0 + (pt_series / 10.0) * 24.0

    if calc_source == "pt_only" or mode == "total_pt":
        return pt_score.clip(35.0, 75.0)

    # 2. 生データスコア
    raw_series = pd.to_numeric(df.get(col_val, pd.Series([np.nan] * n, index=df.index)), errors="coerce")
    valid = raw_series.dropna()
    if valid.empty:
        return pt_score.clip(35.0, 75.0)

    if mode == "deviation":
        # UMA-X偏差値はそのまま偏差値スケール (平均50) として利用
        raw_score = raw_series.fillna(48.0).clip(35.0, 75.0)
    elif mode == "rank_lower_better":
        # 着順予想 (1位〜18位) -> 1位が68, 最下位が42
        max_r = max(float(valid.max()), float(n), 8.0)
        raw_score = 68.0 - ((raw_series.fillna(max_r * 0.65) - 1.0) / max(1.0, max_r - 1.0)) * 26.0
        raw_score = raw_score.clip(38.0, 72.0)
    else:
        # Ω指数, オリジンAI, ウェーブAI など高いほど良い数値 -> レース内ZスコアまたはMinMaxで40〜68に変換
        mean_v = float(valid.mean())
        std_v = float(valid.std(ddof=0))
        if std_v > 1e-6:
            z = (raw_series.fillna(mean_v) - mean_v) / std_v
            raw_score = (52.0 + z * 8.5).clip(38.0, 73.0)
        else:
            raw_score = pd.Series([50.0] * n, index=df.index)

    if calc_source == "raw_only":
        return raw_score.clip(35.0, 75.0)

    # hybrid: 生データ 65% + 獲得ポイント 35%
    return (raw_score * 0.65 + pt_score * 0.35).clip(35.0, 75.0)


def compute_horse_simulation_stats(
    df: pd.DataFrame,
    mapping_config: Dict[str, Any],
    style_overrides: Optional[Dict[int, str]] = None,
) -> pd.DataFrame:
    """
    出馬表DataFrameと連動設定(mapping_config)から各馬のシミュレーション用パラメータを算出する。
    返り値DataFrame列:
      枠番, 馬番, 馬名, 騎手, 斤量, 単勝オッズ, 人気, 合計_pt,
      speed, accel, stamina, guts, overall, style (脚質: 逃/先/差/追)
    """
    active_df = df[df["取消"] == False].copy() if "取消" in df.columns else df.copy()
    if active_df.empty:
        return active_df

    calc_source = mapping_config.get("calc_source", "hybrid")
    weights_map = mapping_config.get("weights", PARAM_MAPPING_PRESETS["🏆 標準バランス（推奨：各指数の特性を適材適所で連動）"]["weights"])

    # 各指標の正規化スコア辞書を作成
    metric_scores: Dict[str, pd.Series] = {}
    for m in SOURCE_METRICS:
        metric_scores[m["key"]] = _normalize_series_to_score(active_df, m, calc_source)

    # 4大能力の加重平均を算出 (50〜99のウイニングポスト風表示値に変換)
    for ab in ABILITY_PARAMS:
        ab_id = ab["id"]
        w_dict: Dict[str, float] = weights_map.get(ab_id, {})
        total_w = sum(float(v) for v in w_dict.values() if float(v) > 0)
        if total_w <= 0:
            raw_ab = metric_scores["合計PT"]
        else:
            acc = pd.Series(0.0, index=active_df.index)
            for m_key, w_val in w_dict.items():
                if float(w_val) > 0 and m_key in metric_scores:
                    acc += metric_scores[m_key] * float(w_val)
            raw_ab = acc / total_w

        # 35〜75 -> ウイニングポスト風の 52〜98 スケールに変換
        scaled = 52.0 + ((raw_ab - 38.0) / 34.0) * 45.0
        active_df[ab_id] = scaled.clip(50.0, 99.0).round(1)

    # 総合評価値 (S〜Cランク判定用)
    active_df["overall"] = (
        active_df["speed"] * 0.30
        + active_df["accel"] * 0.30
        + active_df["stamina"] * 0.20
        + active_df["guts"] * 0.20
    ).round(1)

    # 脚質（逃・先・差・追）の自動判定
    # SP値とAG値のバランス＋馬番からリアルな隊列バランスになるよう割り当て
    sp_diff = active_df["speed"] - active_df["accel"]
    sp_ranks = sp_diff.rank(ascending=False, method="first")
    n_horses = len(active_df)

    styles: List[str] = []
    for idx, row in active_df.iterrows():
        umaban = int(row["馬番"])
        if style_overrides and umaban in style_overrides and style_overrides[umaban] in ("逃", "先", "差", "追"):
            styles.append(style_overrides[umaban])
            continue
        r_pos = float(sp_ranks.loc[idx])
        ratio = r_pos / max(1.0, float(n_horses))
        if r_pos <= max(1.0, round(n_horses * 0.12)):
            styles.append("逃")
        elif ratio <= 0.42:
            styles.append("先")
        elif ratio <= 0.78:
            styles.append("差")
        else:
            styles.append("追")

    active_df["style"] = styles
    return active_df


def run_monte_carlo_simulations(
    sim_df: pd.DataFrame,
    course: Dict[str, Any],
    n_trials: int = 100,
    random_factor: float = 0.25,
) -> pd.DataFrame:
    """
    指定した能力パラメータとコース条件で n_trials 回レースをシミュレーションし、
    各馬の勝率・連対率・3着内率・平均着順を算出する。
    """
    if sim_df.empty:
        return sim_df

    n_horses = len(sim_df)
    dist = course["distance"]
    is_long = dist >= 2000
    is_short = dist <= 1400
    long_straight = course["straight_len"] >= 450

    # コース特性による能力重要度補正
    w_sp = 0.34 if is_short else (0.25 if is_long else 0.30)
    w_ac = 0.35 if long_straight else 0.28
    w_st = 0.28 if is_long else (0.15 if is_short else 0.22)
    w_gu = 1.0 - (w_sp + w_ac + w_st)

    base_scores = (
        sim_df["speed"].to_numpy() * w_sp
        + sim_df["accel"].to_numpy() * w_ac
        + sim_df["stamina"].to_numpy() * w_st
        + sim_df["guts"].to_numpy() * w_gu
    )
    guts_arr = sim_df["guts"].to_numpy()
    styles = sim_df["style"].tolist()

    win_counts = np.zeros(n_horses, dtype=int)
    top2_counts = np.zeros(n_horses, dtype=int)
    top3_counts = np.zeros(n_horses, dtype=int)
    rank_sums = np.zeros(n_horses, dtype=float)

    rng = np.random.default_rng(seed=42)
    noise_scale = 2.0 + random_factor * 14.0  # ランダム要素の大きさ

    for _ in range(n_trials):
        # ペース乱数 (-1.0: スロー前残り 〜 +1.0: ハイペース差し決着)
        pace = rng.normal(0.0, 0.65)
        style_bonus = np.array(
            [
                (-1.8 * pace if s == "逃" else (-0.9 * pace if s == "先" else (1.0 * pace if s == "差" else 1.7 * pace)))
                for s in styles
            ]
        )
        # 勝負根性が高い馬ほど不利・ブレが小さい
        consistency_factor = 1.15 - (guts_arr - 50.0) / 140.0
        trial_noise = rng.normal(0.0, noise_scale, size=n_horses) * consistency_factor

        perf = base_scores + style_bonus + trial_noise
        order = np.argsort(-perf)
        ranks = np.empty(n_horses, dtype=int)
        ranks[order] = np.arange(1, n_horses + 1)

        win_counts[order[0]] += 1
        for idx_top2 in order[: min(2, n_horses)]:
            top2_counts[idx_top2] += 1
        for idx_top3 in order[: min(3, n_horses)]:
            top3_counts[idx_top3] += 1
        rank_sums += ranks

    out = sim_df.copy()
    out["シミュ勝率(%)"] = (win_counts / n_trials * 100.0).round(1)
    out["シミュ連対率(%)"] = (top2_counts / n_trials * 100.0).round(1)
    out["シミュ複勝率(%)"] = (top3_counts / n_trials * 100.0).round(1)
    out["平均着順"] = (rank_sums / n_trials).round(2)

    # 単勝期待値 (単勝オッズ × 勝率)
    def _calc_ev(row: pd.Series) -> Optional[float]:
        odds = row.get("単勝オッズ")
        if odds is None or pd.isna(odds):
            return None
        return round(float(odds) * (float(row["シミュ勝率(%)"]) / 100.0), 2)

    out["単勝期待値"] = out.apply(_calc_ev, axis=1)
    return out.sort_values(by=["シミュ勝率(%)", "シミュ連対率(%)", "overall"], ascending=[False, False, False])


def build_winning_post_html(
    sim_df: pd.DataFrame,
    course: Dict[str, Any],
    waku_style: Dict[int, Tuple[str, str, str]],
    default_view: str = "dynamic",
    default_design: str = "wp",
    random_factor: float = 0.25,
) -> str:
    """
    ウイニングポスト風 インタラクティブHTML5 Canvas レースビューアを生成する。
    - 視点切替: ダイナミックTVカメラ(俯瞰+横追従+直線ズーム) / サイドビュー(横スクロール) / 2Dコース全体俯瞰
    - デザイン切替: ウイニングポスト風 / JRA TV中継風 / レトロアーケード風
    - ファンファーレ＆効果音 (Web Audio API シンセサイザー, ON/OFF対応)
    - リアルタイム実況テロップ & 電光着順掲示板 & 全頭着順表
    """
    horses_payload = []
    for _, row in sim_df.sort_values("馬番").iterrows():
        waku = int(row["枠番"])
        w_bg, w_fg, w_bd = waku_style.get(waku, ("#ffffff", "#1e293b", "#94a3b8"))
        odds_v = row.get("単勝オッズ")
        ninki_v = row.get("人気")
        horses_payload.append(
            {
                "waku": waku,
                "umaban": int(row["馬番"]),
                "name": str(row["馬名"]),
                "jockey": str(row.get("騎手", "")),
                "kinryo": str(row.get("斤量", "")),
                "odds": float(odds_v) if (odds_v is not None and not pd.isna(odds_v)) else 99.9,
                "ninki": int(ninki_v) if (ninki_v is not None and not pd.isna(ninki_v)) else 9,
                "total_pt": int(row.get("合計_pt", 0)),
                "speed": float(row["speed"]),
                "accel": float(row["accel"]),
                "stamina": float(row["stamina"]),
                "guts": float(row["guts"]),
                "overall": float(row["overall"]),
                "style": str(row["style"]),
                "w_bg": w_bg,
                "w_fg": w_fg,
                "w_bd": w_bd,
            }
        )

    data_json = json.dumps(
        {
            "course": course,
            "horses": horses_payload,
            "defaultView": default_view,
            "defaultDesign": default_design,
            "randomFactor": random_factor,
        },
        ensure_ascii=False,
    )

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  * {{ box-sizing: border-box; font-family: "Hiragino Kaku Gothic ProN", "Meiryo", sans-serif; }}
  body {{ margin: 0; padding: 0; background: transparent; color: #f8fafc; user-select: none; }}
  .wp-shell {{
    border-radius: 12px;
    overflow: hidden;
    border: 2px solid #eab308;
    background: linear-gradient(180deg, #090d16 0%, #111827 100%);
    box-shadow: 0 8px 24px rgba(0,0,0,0.45);
  }}
  .wp-shell.design-tv {{
    border: 2px solid #38bdf8;
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
  }}
  .wp-shell.design-retro {{
    border: 3px solid #f43f5e;
    background: #000000;
  }}
  /* 上部コントロールバー */
  .wp-toolbar {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    background: rgba(15, 23, 42, 0.95);
    border-bottom: 1px solid rgba(234, 179, 8, 0.35);
  }}
  .wp-btn-group {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }}
  .wp-btn {{
    cursor: pointer;
    border: 1px solid #475569;
    background: #1e293b;
    color: #f8fafc;
    font-weight: 700;
    font-size: 0.78rem;
    padding: 5px 10px;
    border-radius: 6px;
    transition: all 0.15s;
  }}
  .wp-btn:hover {{ background: #334155; border-color: #94a3b8; }}
  .wp-btn.primary {{
    background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
    border-color: #f87171;
    color: #fff;
    font-size: 0.84rem;
    padding: 6px 14px;
  }}
  .wp-btn.primary:hover {{ filter: brightness(1.12); }}
  .wp-btn.active {{
    background: #eab308;
    color: #0f172a;
    border-color: #fef08a;
  }}
  .wp-select {{
    background: #ffffff;
    color: #0f172a;
    font-weight: 700;
    font-size: 0.78rem;
    padding: 4px 8px;
    border-radius: 6px;
    border: 1px solid #94a3b8;
  }}
  /* キャンバス領域 */
  .canvas-wrap {{
    position: relative;
    width: 100%;
    height: 430px;
    background: #064e3b;
    overflow: hidden;
  }}
  canvas#raceCanvas {{
    width: 100%;
    height: 100%;
    display: block;
  }}
  /* 実況メッセージウィンドウ (ウイニングポスト風) */
  .commentary-box {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    min-height: 64px;
    background: linear-gradient(180deg, #090d16 0%, #172033 100%);
    border-top: 2px solid #eab308;
    border-bottom: 1px solid #334155;
  }}
  .wp-shell.design-tv .commentary-box {{
    background: linear-gradient(90deg, #0c4a6e 0%, #0f172a 100%);
    border-top: 2px solid #38bdf8;
  }}
  .wp-shell.design-retro .commentary-box {{
    background: #111111;
    border-top: 3px double #22c55e;
  }}
  .announcer-badge {{
    flex-shrink: 0;
    background: linear-gradient(135deg, #eab308 0%, #ca8a04 100%);
    color: #0f172a;
    font-weight: 900;
    font-size: 0.78rem;
    padding: 6px 10px;
    border-radius: 6px;
    text-align: center;
    box-shadow: 0 2px 6px rgba(0,0,0,0.4);
  }}
  .commentary-text {{
    font-size: 1.02rem;
    font-weight: 800;
    color: #fef08a;
    line-height: 1.4;
    text-shadow: 0 2px 4px rgba(0,0,0,0.8);
    letter-spacing: 0.02em;
  }}
  /* 下部 着順掲示板＆全頭結果パネル */
  .result-panel {{
    padding: 10px 14px;
    background: #0f172a;
    max-height: 250px;
    overflow-y: auto;
  }}
  .result-title {{
    font-size: 0.85rem;
    font-weight: 800;
    color: #eab308;
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  table.res-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.78rem;
    color: #f8fafc;
  }}
  table.res-table th {{
    background: #1e293b;
    color: #cbd5e1;
    padding: 4px 6px;
    border: 1px solid #334155;
    text-align: center;
  }}
  table.res-table td {{
    padding: 4px 6px;
    border: 1px solid #1e293b;
    text-align: center;
  }}
  .waku-pill {{
    display: inline-block;
    width: 20px;
    height: 20px;
    line-height: 18px;
    border-radius: 4px;
    font-weight: 800;
    text-align: center;
    font-size: 0.74rem;
  }}
  @media (max-width: 768px) {{
    .canvas-wrap {{ height: 350px; }}
    .commentary-text {{ font-size: 0.88rem; }}
    .wp-btn {{ font-size: 0.72rem; padding: 4px 8px; }}
  }}
</style>
</head>
<body>
<div id="wpShell" class="wp-shell">
  <!-- ツールバー -->
  <div class="wp-toolbar">
    <div class="wp-btn-group">
      <button id="btnStart" class="wp-btn primary">🎺 ファンファーレ＆発走</button>
      <button id="btnPause" class="wp-btn">⏯️ 一時停止/再開</button>
      <button id="btnReplay" class="wp-btn">🔄 もう1回走らせる(別展開)</button>
      <button id="btnSound" class="wp-btn active">🔊 音: ON</button>
    </div>
    <div class="wp-btn-group">
      <label style="font-size:0.75rem;color:#cbd5e1;font-weight:700;">📷 視点:</label>
      <select id="selView" class="wp-select">
        <option value="dynamic">🎬 ダイナミックTV中継 (俯瞰＋横＋直線ズーム)</option>
        <option value="side">🎥 ウイニングポスト風 サイドビュー (横スクロール)</option>
        <option value="top">🏟️ 競馬場コース全体 2D俯瞰ビュー</option>
      </select>
      <label style="font-size:0.75rem;color:#cbd5e1;font-weight:700;">🎨 デザイン:</label>
      <select id="selDesign" class="wp-select">
        <option value="wp">🏆 ウイニングポスト風</option>
        <option value="tv">📺 JRA TV中継風</option>
        <option value="retro">🕹️ レトロアーケード風</option>
      </select>
      <label style="font-size:0.75rem;color:#cbd5e1;font-weight:700;">⏩ 速度:</label>
      <select id="selSpeed" class="wp-select">
        <option value="1">1.0x (標準)</option>
        <option value="1.6">1.6x (快適)</option>
        <option value="2.5">2.5x (高速)</option>
        <option value="0.5">0.5x (スロー)</option>
      </select>
    </div>
  </div>

  <!-- キャンバス -->
  <div class="canvas-wrap">
    <canvas id="raceCanvas"></canvas>
  </div>

  <!-- 実況テロップ枠 -->
  <div class="commentary-box">
    <div class="announcer-badge">🎙️ 実況</div>
    <div id="commText" class="commentary-text">
      各馬ゲートに収まります…「🎺 ファンファーレ＆発走」ボタンを押すとレースがスタートします！
    </div>
  </div>

  <!-- 着順結果テーブル -->
  <div class="result-panel">
    <div class="result-title">
      <span id="resHeader">🏁 レース結果・道中順位速報</span>
      <span id="paceBadge" style="font-size:0.76rem;color:#93c5fd;">待機中</span>
    </div>
    <div id="resTableWrap"></div>
  </div>
</div>

<script>
(() => {{
  const DATA = {data_json};
  const course = DATA.course;
  const baseHorses = DATA.horses;

  const shell = document.getElementById("wpShell");
  const canvas = document.getElementById("raceCanvas");
  const ctx = canvas.getContext("2d");
  const commText = document.getElementById("commText");
  const resTableWrap = document.getElementById("resTableWrap");
  const resHeader = document.getElementById("resHeader");
  const paceBadge = document.getElementById("paceBadge");

  const selView = document.getElementById("selView");
  const selDesign = document.getElementById("selDesign");
  const selSpeed = document.getElementById("selSpeed");
  const btnStart = document.getElementById("btnStart");
  const btnPause = document.getElementById("btnPause");
  const btnReplay = document.getElementById("btnReplay");
  const btnSound = document.getElementById("btnSound");

  selView.value = DATA.defaultView || "dynamic";
  selDesign.value = DATA.defaultDesign || "wp";

  let viewMode = selView.value;
  let designMode = selDesign.value;
  let simSpeed = parseFloat(selSpeed.value) || 1.0;
  let soundEnabled = true;

  function applyDesignClass() {{
    shell.className = "wp-shell";
    if (designMode === "tv") shell.classList.add("design-tv");
    if (designMode === "retro") shell.classList.add("design-retro");
  }}
  applyDesignClass();

  selView.addEventListener("change", () => {{ viewMode = selView.value; }});
  selDesign.addEventListener("change", () => {{ designMode = selDesign.value; applyDesignClass(); }});
  selSpeed.addEventListener("change", () => {{ simSpeed = parseFloat(selSpeed.value) || 1.0; }});
  btnSound.addEventListener("click", () => {{
    soundEnabled = !soundEnabled;
    btnSound.textContent = soundEnabled ? "🔊 音: ON" : "🔇 音: OFF";
    btnSound.classList.toggle("active", soundEnabled);
  }});

  // roundRect ポリフィル (古いブラウザ対策)
  if (!CanvasRenderingContext2D.prototype.roundRect) {{
    CanvasRenderingContext2D.prototype.roundRect = function(x, y, w, h, r) {{
      const rad = Math.min(r || 0, w / 2, h / 2);
      this.moveTo(x + rad, y);
      this.arcTo(x + w, y, x + w, y + h, rad);
      this.arcTo(x + w, y + h, x, y + h, rad);
      this.arcTo(x, y + h, x, y, rad);
      this.arcTo(x, y, x + w, y, rad);
      this.closePath();
      return this;
    }};
  }}

  // -------------------------------------------------------------------------
  // Web Audio API シンセサイザー (ファンファーレ・ゲート音・蹄音・歓声)
  // -------------------------------------------------------------------------
  let audioCtx = null;
  function ensureAudio() {{
    if (!soundEnabled) return null;
    try {{
      if (!audioCtx) {{
        const AC = window.AudioContext || window.webkitAudioContext;
        if (AC) audioCtx = new AC();
      }}
      if (audioCtx && audioCtx.state === "suspended") audioCtx.resume();
      return audioCtx;
    }} catch (e) {{
      return null;
    }}
  }}

  function playNote(freq, startOffset, duration, type = "triangle", gainVal = 0.12) {{
    try {{
      const ac = ensureAudio();
      if (!ac) return;
      const osc = ac.createOscillator();
      const g = ac.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, ac.currentTime + startOffset);
      g.gain.setValueAtTime(0.001, ac.currentTime + startOffset);
      g.gain.exponentialRampToValueAtTime(gainVal, ac.currentTime + startOffset + 0.02);
      g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + startOffset + duration);
      osc.connect(g);
      g.connect(ac.destination);
      osc.start(ac.currentTime + startOffset);
      osc.stop(ac.currentTime + startOffset + duration + 0.02);
    }} catch (e) {{}}
  }}

  function playFanfare() {{
    if (!soundEnabled) return;
    const notes = [
      [523.25, 0.0, 0.12], [659.25, 0.13, 0.12], [783.99, 0.26, 0.12],
      [1046.50, 0.39, 0.28], [783.99, 0.70, 0.12], [1046.50, 0.85, 0.40]
    ];
    notes.forEach(([f, st, d]) => playNote(f, st, d, "sawtooth", 0.09));
  }}

  function playGateSound() {{
    try {{
      const ac = ensureAudio();
      if (!ac) return;
      const bufferSize = Math.floor(ac.sampleRate * 0.22);
      const buffer = ac.createBuffer(1, bufferSize, ac.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < bufferSize; i++) {{
        data[i] = (Math.random() * 2 - 1) * Math.exp(-i / (ac.sampleRate * 0.06));
      }}
      const noise = ac.createBufferSource();
      noise.buffer = buffer;
      const g = ac.createGain();
      g.gain.value = 0.22;
      noise.connect(g);
      g.connect(ac.destination);
      noise.start();
    }} catch (e) {{}}
  }}

  let lastHoofTime = 0;
  let lastCommPhase = "";
  let lastTableUpdateMs = 0;
  let fanfareTimer = null;

  function playHoofTick(nowMs, isSpurt) {{
    if (!soundEnabled) return;
    const interval = isSpurt ? 110 : 155;
    if (nowMs - lastHoofTime < interval) return;
    lastHoofTime = nowMs;
    playNote(isSpurt ? 145 : 115, 0, 0.035, "sine", 0.04);
  }}

  // -------------------------------------------------------------------------
  // レース物理・展開シミュレーション状態
  // -------------------------------------------------------------------------
  const totalDist = course.distance || 1600;
  let runners = [];
  let raceState = "ready"; // "ready", "fanfare", "running", "finished"
  let paused = false;
  let elapsedSimSec = 0;
  let paceType = "平均ペース";
  let paceFactor = 0.0; // -1: スロー, +1: ハイ
  let finishOrder = [];
  let particles = [];

  function initRace(withVariance = true) {{
    if (fanfareTimer) {{
      clearTimeout(fanfareTimer);
      fanfareTimer = null;
    }}
    particles = [];
    finishOrder = [];
    elapsedSimSec = 0;
    lastCommPhase = "";
    lastTableUpdateMs = 0;
    const rf = withVariance ? (DATA.randomFactor ?? 0.25) : 0.08;
    paceFactor = (Math.random() - 0.5) * 1.4 * (rf / 0.25);
    paceType = paceFactor > 0.32 ? "ハイペース" : (paceFactor < -0.32 ? "スローペース" : "平均ペース");
    paceBadge.textContent = `展開予測: ${{paceType}} (${{course.surface}}${{totalDist}}m・${{course.turn}})`;

    const baseSpeedMps = course.surface === "ダート" ? 16.3 : 16.95;

    runners = baseHorses.map((h, idx) => {{
      const gFactor = 1.15 - (h.guts - 50) / 150;
      const randStart = (Math.random() - 0.48) * 1.6 * rf * gFactor;
      const randMid = (Math.random() - 0.5) * 2.2 * rf * gFactor;
      const randSpurt = (Math.random() - 0.46) * 2.8 * rf * gFactor;

      let styleTargetPos = 0.0;
      if (h.style === "逃") styleTargetPos = 0.0;
      else if (h.style === "先") styleTargetPos = 0.24 + (idx % 3) * 0.05;
      else if (h.style === "差") styleTargetPos = 0.55 + (idx % 4) * 0.06;
      else styleTargetPos = 0.82 + (idx % 3) * 0.06;

      let paceBonus = 0;
      if (h.style === "逃") paceBonus = -paceFactor * 0.25;
      else if (h.style === "先") paceBonus = -paceFactor * 0.12;
      else if (h.style === "差") paceBonus = paceFactor * 0.15;
      else paceBonus = paceFactor * 0.26;

      return {{
        ...h,
        dist: 0,
        speedMps: 0,
        baseSpeedMps,
        lane: idx,
        lateralY: idx,
        styleTargetPos,
        randStart,
        randMid,
        randSpurt,
        paceBonus,
        staminaLeft: 100,
        isSpurting: false,
        finished: false,
        finishTime: null,
        last3FTime: null,
        passDistLast3F: null,
        stridePhase: Math.random() * Math.PI * 2,
      }};
    }});

    renderLiveTable(0);
  }}

  function startRaceSequence() {{
    initRace(true);
    paused = false;
    raceState = "fanfare";
    commText.textContent = `🎺 ファンファーレが鳴り響きます！ ${{course.venue}}${{course.race_num}}R「${{course.race_name}}」(${{course.surface}}${{totalDist}}m) まもなく発走！`;
    playFanfare();
    fanfareTimer = setTimeout(() => {{
      raceState = "running";
      playGateSound();
      commText.textContent = `🔔 スタートしました！ 全馬一斉にゲートを飛び出しました！`;
    }}, 900);
  }}

  btnStart.addEventListener("click", startRaceSequence);
  btnReplay.addEventListener("click", startRaceSequence);
  btnPause.addEventListener("click", () => {{
    if (raceState === "running") {{
      paused = !paused;
      btnPause.textContent = paused ? "▶️ 再開する" : "⏸️ 一時停止";
    }} else if (raceState === "ready" || raceState === "finished") {{
      startRaceSequence();
    }}
  }});
  canvas.addEventListener("click", () => {{
    if (raceState === "ready" || raceState === "finished") {{
      startRaceSequence();
    }}
  }});

  // -------------------------------------------------------------------------
  // 実況メッセージ更新ロジック
  // -------------------------------------------------------------------------
  function updateCommentary(leadHorse, secondHorse, progress) {{
    let phase = "";
    if (progress < 0.08) phase = "start";
    else if (progress < 0.32) phase = "early";
    else if (progress < 0.58) phase = "mid";
    else if (progress < 0.74) phase = "corner4";
    else if (progress < 0.90) phase = "straight";
    else if (progress < 0.995) phase = "final100";
    else phase = "goal";

    if (phase === lastCommPhase) return;
    lastCommPhase = phase;

    const lName = `${{leadHorse.umaban}}番${{leadHorse.name}}`;
    const sName = secondHorse ? `${{secondHorse.umaban}}番${{secondHorse.name}}` : "";

    // 後方から猛追している馬を探す
    const spurters = runners.filter(r => r.isSpurting && r.umaban !== leadHorse.umaban)
                            .sort((a, b) => b.speedMps - a.speedMps);
    const topSpurter = spurters[0];

    if (phase === "start") {{
      commText.textContent = `🔔 スタートしました！ まずは ${{lName}}(${{leadHorse.jockey}}) が好ダッシュを決めてハナを奪います！`;
    }} else if (phase === "early") {{
      commText.textContent = `先頭は ${{lName}}！ 2番手に ${{sName}} がつけ、前半は【${{paceType}}】で流れています！`;
    }} else if (phase === "mid") {{
      commText.textContent = `向正面の中間点を通過！ 先頭は依然として ${{lName}}、後続の有力馬はじっくり脚を溜めています！`;
    }} else if (phase === "corner4") {{
      commText.textContent = `🔥 第3〜4コーナー中間！ 後続勢が一斉に仕掛けて馬群が凝縮！ さあ最後の直線コースへ！`;
    }} else if (phase === "straight") {{
      if (topSpurter) {{
        commText.textContent = `⚡ 直線コース！ 粘る ${{lName}}！ 外からもの凄い末脚で ${{topSpurter.umaban}}番${{topSpurter.name}}(${{topSpurter.jockey}}) が飛んでくる！！`;
      }} else {{
        commText.textContent = `⚡ 最後の直線に入った！ 先頭は ${{lName}}！ 内から外から各馬が一斉に末脚を伸ばす！`;
      }}
    }} else if (phase === "final100") {{
      commText.textContent = `🏁 残り200mを切った！ ${{lName}} か、${{sName}} か！？ ゴール前の大激戦！！`;
    }}
  }}

  // -------------------------------------------------------------------------
  // 1フレーム物理更新
  // -------------------------------------------------------------------------
  function stepPhysics(dtReal) {{
    if (raceState !== "running" || paused) return;

    // 観戦しやすいように距離に応じて時間スケールを調整 (1レース約22〜28秒で決着)
    const timeScale = (totalDist / 400.0) * simSpeed;
    const dt = dtReal * timeScale;
    elapsedSimSec += dt;

    // 現在の先頭距離
    let maxDist = 0;
    runners.forEach(r => {{ if (r.dist > maxDist) maxDist = r.dist; }});
    const raceProgress = Math.min(1.0, maxDist / totalDist);

    runners.forEach(r => {{
      if (r.finished) return;

      const prog = r.dist / totalDist;
      if (r.dist >= totalDist - 600 && r.passDistLast3F === null) {{
        r.passDistLast3F = elapsedSimSec;
      }}

      let targetSpeed = r.baseSpeedMps;

      if (prog < 0.12) {{
        // スタートダッシュ区間
        const dashSkill = (r.speed - 65) * 0.032 + (r.style === "逃" ? 0.55 : (r.style === "先" ? 0.25 : (r.style === "差" ? -0.15 : -0.38)));
        targetSpeed += dashSkill + r.randStart * 0.22;
      }} else if (prog < 0.66) {{
        // 道中巡航区間 (脚質ごとの隊列形成)
        const currentGap = maxDist - r.dist;
        const desiredGap = r.styleTargetPos * 26.0;
        const posAdjust = (currentGap - desiredGap) * 0.09;
        const cruiseSkill = (r.speed - 70) * 0.022 + (r.stamina - 70) * 0.015;
        targetSpeed += cruiseSkill + posAdjust + r.randMid * 0.12 + paceFactor * (r.style === "逃" ? 0.18 : 0.05);
        r.isSpurting = false;
      }} else {{
        // 勝負どころ（残り34%〜ゴール：末脚・瞬発力・スタミナ・勝負根性勝負！）
        r.isSpurting = (r.accel >= 74 || r.overall >= 75 || prog > 0.75);
        const spurtBoost =
          (r.accel - 68) * 0.048 +
          (r.speed - 68) * 0.026 +
          (r.stamina - 68) * 0.024 +
          (r.guts - 68) * 0.024 +
          r.paceBonus +
          r.randSpurt * 0.22;

        // 差し・追い込み馬は直線で外に持ち出して末脚加算
        const styleLateBoost = (r.style === "追" ? 0.52 : (r.style === "差" ? 0.34 : (r.style === "先" ? 0.08 : -0.05)));
        targetSpeed += spurtBoost + styleLateBoost;

        // 直線で外に持ち出すレーン移動
        if (r.style === "差" || r.style === "追") {{
          r.lateralY += (Math.min(runners.length - 1, r.lane + 2.5) - r.lateralY) * 0.04;
        }}
      }}

      // なめらかに速度追従
      r.speedMps += (targetSpeed - r.speedMps) * Math.min(1.0, dt * 3.5);
      r.dist += r.speedMps * dt;
      r.stridePhase += r.speedMps * dt * 1.45;

      // 砂・芝パーティクル生成
      if (Math.random() < 0.35) {{
        particles.push({{
          dist: r.dist - 1.5,
          lane: r.lateralY,
          vx: -Math.random() * 4 - 2,
          vy: (Math.random() - 0.5) * 2,
          life: 1.0,
          isSpurt: r.isSpurting
        }});
      }}

      // ゴール判定
      if (r.dist >= totalDist) {{
        const overshoot = r.dist - totalDist;
        const exactTime = elapsedSimSec - (overshoot / Math.max(10, r.speedMps));
        r.dist = totalDist + finishOrder.length * 0.15;
        r.finished = true;
        r.finishTime = exactTime;
        const raw3F = r.passDistLast3F ? (exactTime - r.passDistLast3F) : 34.5;
        r.last3FTime = Math.max(32.2, Math.min(38.9, raw3F));
        finishOrder.push(r);
      }}
    }});

    // パーティクル更新
    for (let i = particles.length - 1; i >= 0; i--) {{
      particles[i].life -= dtReal * 2.4;
      if (particles[i].life <= 0) particles.splice(i, 1);
    }}

    // 順位ソート
    const sorted = [...runners].sort((a, b) => {{
      if (a.finished && b.finished) return a.finishTime - b.finishTime;
      if (a.finished) return -1;
      if (b.finished) return 1;
      return b.dist - a.dist;
    }});

    if (sorted.length > 0) {{
      updateCommentary(sorted[0], sorted[1], raceProgress);
    }}

    // 全馬ゴール完了チェック
    if (finishOrder.length === runners.length && raceState === "running") {{
      raceState = "finished";
      const w = finishOrder[0];
      const s = finishOrder[1];
      const marginSec = s ? (s.finishTime - w.finishTime) : 0;
      const marginTxt = formatMargin(marginSec);
      commText.textContent = `🏆 ゴールイン！！ 勝ったのは ${{w.umaban}}番 ${{w.name}}(${{w.jockey}})！ 2着 ${{s ? s.umaban + '番' + s.name : ''}} に【${{marginTxt}}】差をつけて見事1着！！`;
      renderLiveTable();
    }}
  }}

  function formatRaceTime(sec) {{
    if (!sec || isNaN(sec)) return "-";
    const m = Math.floor(sec / 60);
    const s = (sec % 60).toFixed(1).padStart(4, "0");
    return m > 0 ? `${{m}}:${{s}}` : `${{s}}秒`;
  }}

  function formatMargin(diffSec) {{
    if (diffSec <= 0.02) return "ハナ";
    if (diffSec <= 0.05) return "アタマ";
    if (diffSec <= 0.09) return "クビ";
    if (diffSec <= 0.14) return "1/2馬身";
    if (diffSec <= 0.20) return "3/4馬身";
    if (diffSec <= 0.28) return "1馬身";
    if (diffSec <= 0.42) return "1馬身1/2";
    if (diffSec <= 0.55) return "2馬身";
    if (diffSec <= 0.80) return "3馬身";
    return `${{Math.min(10, Math.round(diffSec / 0.18))}}馬身`;
  }}

  // -------------------------------------------------------------------------
  // 下部テーブル描画 (確定着順 or リアルタイム順位)
  // -------------------------------------------------------------------------
  function renderLiveTable(nowMs = 0) {{
    if (raceState === "running" && nowMs - lastTableUpdateMs < 350) return;
    lastTableUpdateMs = nowMs;

    const sorted = [...runners].sort((a, b) => {{
      if (a.finished && b.finished) return a.finishTime - b.finishTime;
      if (a.finished) return -1;
      if (b.finished) return 1;
      return b.dist - a.dist;
    }});

    resHeader.textContent = raceState === "finished"
      ? "🏆 確定着順・走破タイム・上がり3F一覧"
      : "🏇 リアルタイム道中順位＆能力パラメータ一覧";

    let rowsHtml = "";
    sorted.forEach((r, idx) => {{
      const rank = idx + 1;
      const prev = idx > 0 ? sorted[idx - 1] : null;
      let marginStr = "-";
      if (r.finished && prev && prev.finished && idx > 0) {{
        marginStr = formatMargin(r.finishTime - prev.finishTime);
      }} else if (!r.finished && prev) {{
        marginStr = `${{(prev.dist - r.dist).toFixed(1)}}m`;
      }}

      const medal = rank === 1 ? "🥇 1着" : (rank === 2 ? "🥈 2着" : (rank === 3 ? "🥉 3着" : `${{rank}}着`));
      const rowBg = rank === 1 ? "rgba(234,179,8,0.16)" : (rank <= 3 ? "rgba(56,189,248,0.10)" : "transparent");

      rowsHtml += `<tr style="background:${{rowBg}};">
        <td style="font-weight:900;color:${{rank===1?'#fef08a':'#f8fafc'}};">${{medal}}</td>
        <td><span class="waku-pill" style="background:${{r.w_bg}};color:${{r.w_fg}};border:1px solid ${{r.w_bd}};">${{r.waku}}</span></td>
        <td style="font-weight:800;">${{r.umaban}}</td>
        <td style="text-align:left;font-weight:800;color:#ffffff;">${{r.name}}</td>
        <td style="color:#cbd5e1;">${{r.jockey}}</td>
        <td><span style="background:#334155;padding:1px 6px;border-radius:4px;font-weight:700;">${{r.style}}</span></td>
        <td style="font-weight:800;color:#fca5a5;">${{r.total_pt}}pt</td>
        <td style="color:#93c5fd;">⚡${{r.speed}} / 🔥${{r.accel}} / 💪${{r.stamina}} / ⚔️${{r.guts}}</td>
        <td style="font-weight:800;color:#fef08a;">${{r.finishTime ? formatRaceTime(r.finishTime) : Math.round(r.dist) + 'm'}}</td>
        <td>${{marginStr}}</td>
        <td style="color:${{r.last3FTime && r.last3FTime <= 34.0 ? '#4ade80' : '#cbd5e1'}};font-weight:700;">
          ${{r.last3FTime ? r.last3FTime.toFixed(1) : '-'}}
        </td>
      </tr>`;
    }});

    resTableWrap.innerHTML = `<table class="res-table">
      <thead>
        <tr>
          <th>順位</th><th>枠</th><th>馬番</th><th style="text-align:left;">馬名</th><th>騎手</th>
          <th>脚質</th><th>合計PT</th><th>連動能力値 (SP/瞬発/スタ/根性)</th><th>タイム/位置</th><th>着差</th><th>上り3F</th>
        </tr>
      </thead>
      <tbody>${{rowsHtml}}</tbody>
    </table>`;
  }}

  // -------------------------------------------------------------------------
  // Canvas 描画処理 (サイドビュー / 2Dコース全体俯瞰 / ダイナミックTVカメラ)
  // -------------------------------------------------------------------------
  function resizeCanvas() {{
    const rect = canvas.parentElement.getBoundingClientRect();
    if (canvas.width !== Math.floor(rect.width) || canvas.height !== Math.floor(rect.height)) {{
      canvas.width = Math.floor(rect.width);
      canvas.height = Math.floor(rect.height);
    }}
  }}

  function drawHorseSprite(x, y, r, scale = 1.0) {{
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(scale, scale);

    // 末脚爆発オーラ (ウイニングポスト風の青い風/炎エフェクト)
    if (r.isSpurting && !r.finished && raceState === "running") {{
      const grad = ctx.createRadialGradient(-6, -8, 2, -10, -8, 34);
      grad.addColorStop(0, "rgba(56, 189, 248, 0.75)");
      grad.addColorStop(0.5, "rgba(234, 179, 8, 0.40)");
      grad.addColorStop(1, "rgba(56, 189, 248, 0)");
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.ellipse(-10, -8, 34, 15, 0, 0, Math.PI * 2);
      ctx.fill();
    }}

    // 影
    ctx.fillStyle = "rgba(0,0,0,0.35)";
    ctx.beginPath();
    ctx.ellipse(0, 4, 16, 4.5, 0, 0, Math.PI * 2);
    ctx.fill();

    const legSwing = (raceState === "running" && !r.finished) ? Math.sin(r.stridePhase) * 8 : 0;

    // 脚
    ctx.strokeStyle = "#451a03";
    ctx.lineWidth = 2.6;
    ctx.beginPath();
    ctx.moveTo(-8, -4); ctx.lineTo(-12 - legSwing, 4);
    ctx.moveTo(-4, -4); ctx.lineTo(-4 + legSwing * 0.7, 4);
    ctx.moveTo(7, -4);  ctx.lineTo(11 + legSwing, 4);
    ctx.moveTo(4, -4);  ctx.lineTo(4 - legSwing * 0.7, 4);
    ctx.stroke();

    // 馬体 (鹿毛/黒鹿毛/芦毛を馬番で変化)
    const coats = ["#78350f", "#451a03", "#92400e", "#3f2e21", "#cbd5e1", "#57534e"];
    const coatCol = coats[r.umaban % coats.length];
    ctx.fillStyle = coatCol;
    ctx.beginPath();
    ctx.ellipse(0, -8, 13, 6.5, 0, 0, Math.PI * 2);
    ctx.fill();

    // 首・頭
    ctx.beginPath();
    ctx.moveTo(8, -10);
    ctx.lineTo(17, -18 + legSwing * 0.15);
    ctx.lineTo(22, -15 + legSwing * 0.15);
    ctx.lineTo(12, -5);
    ctx.closePath();
    ctx.fill();

    // 尻尾
    ctx.strokeStyle = "#1c1917";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(-12, -10);
    ctx.quadraticCurveTo(-20, -12, -23, -6 - legSwing * 0.3);
    ctx.stroke();

    // ゼッケン (JRA枠番カラー)
    ctx.fillStyle = r.w_bg;
    ctx.strokeStyle = r.w_bd;
    ctx.lineWidth = 1;
    ctx.fillRect(-6, -13, 11, 8);
    ctx.strokeRect(-6, -13, 11, 8);
    ctx.fillStyle = r.w_fg;
    ctx.font = "bold 7.5px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(String(r.umaban), -0.5, -6.5);

    // 騎手胴体＆帽子 (枠番カラー)
    ctx.fillStyle = r.w_bg;
    ctx.beginPath();
    ctx.ellipse(1, -17, 5, 4, -0.3, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = r.w_bd;
    ctx.stroke();

    // 騎手ヘルメット
    ctx.fillStyle = r.w_bg;
    ctx.beginPath();
    ctx.arc(6, -21, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    // 馬名＆馬番プレート (頭上)
    const labelTxt = `${{r.umaban}} ${{r.name.slice(0, 6)}}`;
    ctx.font = "bold 10.5px sans-serif";
    const tw = ctx.measureText(labelTxt).width;
    const bx = -tw / 2 - 5;
    const by = -38;
    ctx.fillStyle = "rgba(15, 23, 42, 0.86)";
    ctx.strokeStyle = r.isSpurting ? "#38bdf8" : r.w_bg;
    ctx.lineWidth = r.isSpurting ? 1.8 : 1.2;
    ctx.beginPath();
    ctx.roundRect(bx, by, tw + 10, 14, 4);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = r.isSpurting ? "#fef08a" : "#ffffff";
    ctx.textAlign = "center";
    ctx.fillText(labelTxt, 0, by + 10.5);

    ctx.restore();
  }}

  function drawSideView(W, H, isZoomFinal) {{
    const isDirt = course.surface === "ダート";
    // 空＆観客席スタンド背景
    const skyGrad = ctx.createLinearGradient(0, 0, 0, H * 0.28);
    if (designMode === "retro") {{
      skyGrad.addColorStop(0, "#1d4ed8");
      skyGrad.addColorStop(1, "#60a5fa");
    }} else {{
      skyGrad.addColorStop(0, "#0ea5e9");
      skyGrad.addColorStop(1, "#bae6fd");
    }}
    ctx.fillStyle = skyGrad;
    ctx.fillRect(0, 0, W, H * 0.28);

    // 遠景スタンド
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(0, H * 0.14, W, H * 0.14);
    ctx.fillStyle = "#334155";
    for (let sx = 0; sx < W; sx += 45) {{
      ctx.fillRect(sx + 4, H * 0.16, 36, H * 0.09);
    }}

    // カメラ中心距離 (先頭集団を追従)
    let leadDist = 0;
    runners.forEach(r => {{ if (r.dist > leadDist) leadDist = r.dist; }});
    const camDist = Math.min(totalDist, Math.max(20, leadDist - 14));
    const pxPerMeter = isZoomFinal ? 15.5 : 11.5;
    const screenLeadX = W * 0.72;

    // コース路面 (芝 or ダート)
    const trackTop = H * 0.28;
    const trackH = H - trackTop;
    const surfGrad = ctx.createLinearGradient(0, trackTop, 0, H);
    if (isDirt) {{
      surfGrad.addColorStop(0, "#92400e");
      surfGrad.addColorStop(0.5, "#b45309");
      surfGrad.addColorStop(1, "#78350f");
    }} else {{
      surfGrad.addColorStop(0, "#15803d");
      surfGrad.addColorStop(0.5, "#16a34a");
      surfGrad.addColorStop(1, "#14532d");
    }}
    ctx.fillStyle = surfGrad;
    ctx.fillRect(0, trackTop, W, trackH);

    // 芝のストライプ模様＆ハロン棒描画
    const minVisibleM = Math.max(0, Math.floor((camDist - screenLeadX / pxPerMeter) / 20) * 20);
    const maxVisibleM = Math.ceil((camDist + (W - screenLeadX) / pxPerMeter) / 20) * 20;

    for (let m = minVisibleM; m <= maxVisibleM; m += 20) {{
      const sx = screenLeadX + (m - camDist) * pxPerMeter;
      // 芝目ストライプ
      ctx.fillStyle = "rgba(255,255,255,0.04)";
      ctx.fillRect(sx, trackTop, 10 * pxPerMeter, trackH);

      // 残り距離標識 (200mごと)
      const rem = totalDist - m;
      if (rem >= 0 && rem % 200 === 0 && rem <= totalDist) {{
        // 内ラチ支柱
        ctx.fillStyle = rem === 0 ? "#eab308" : "#f8fafc";
        ctx.fillRect(sx - 2, trackTop - 22, 4, 26);

        if (rem === 0) {{
          // ゴール板 (ウイニングポスト風の蹄鉄型ゴール板)
          ctx.strokeStyle = "#eab308";
          ctx.lineWidth = 4;
          ctx.beginPath();
          ctx.arc(sx, trackTop - 26, 16, 0.2 * Math.PI, 0.8 * Math.PI, true);
          ctx.stroke();
          ctx.fillStyle = "#dc2626";
          ctx.fillRect(sx - 22, trackTop - 44, 44, 15);
          ctx.fillStyle = "#ffffff";
          ctx.font = "bold 10px sans-serif";
          ctx.textAlign = "center";
          ctx.fillText("GOAL", sx, trackTop - 33);

          // ゴールライン
          ctx.strokeStyle = "rgba(254, 240, 138, 0.75)";
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.moveTo(sx, trackTop);
          ctx.lineTo(sx, H);
          ctx.stroke();
        }} else {{
          ctx.fillStyle = rem <= 400 ? "#dc2626" : "#1d4ed8";
          ctx.fillRect(sx - 18, trackTop - 32, 36, 15);
          ctx.fillStyle = "#ffffff";
          ctx.font = "bold 9.5px sans-serif";
          ctx.textAlign = "center";
          ctx.fillText(`${{rem}}m`, sx, trackTop - 21);
        }}
      }}
    }}

    // 内ラチ白い柵
    ctx.fillStyle = "#f8fafc";
    ctx.fillRect(0, trackTop, W, 5);

    // パーティクル描画
    const nRunners = Math.max(1, runners.length);
    particles.forEach(p => {{
      const px = screenLeadX + (p.dist - camDist) * pxPerMeter;
      const py = trackTop + 34 + (p.lane / nRunners) * (trackH - 54);
      if (px < -20 || px > W + 20) return;
      ctx.fillStyle = p.isSpurt
        ? `rgba(56, 189, 248, ${{p.life * 0.7}})`
        : (isDirt ? `rgba(217, 119, 6, ${{p.life * 0.6}})` : `rgba(74, 222, 128, ${{p.life * 0.6}})`);
      ctx.beginPath();
      ctx.arc(px, py, p.isSpurt ? 3.5 : 2.5, 0, Math.PI * 2);
      ctx.fill();
    }});

    // 各馬を奥(内ラチ)から手前(外ラチ)の順で描画
    const sortedByDepth = [...runners].sort((a, b) => a.lateralY - b.lateralY);
    sortedByDepth.forEach(r => {{
      const hx = screenLeadX + (r.dist - camDist) * pxPerMeter;
      const hy = trackTop + 36 + (r.lateralY / nRunners) * (trackH - 56);
      if (hx < -80 || hx > W + 80) return;
      drawHorseSprite(hx, hy, r, isZoomFinal ? 1.18 : 1.0);
    }});

    // 直線坂・最終局面での集中線エフェクト
    if (isZoomFinal && raceState === "running") {{
      ctx.strokeStyle = "rgba(255, 255, 255, 0.14)";
      ctx.lineWidth = 1.5;
      for (let i = 0; i < 12; i++) {{
        const ly = (i * 37 + Math.floor(elapsedSimSec * 60)) % H;
        ctx.beginPath();
        ctx.moveTo(0, ly);
        ctx.lineTo(W * 0.22, ly);
        ctx.stroke();
      }}
    }}
  }}

  // -------------------------------------------------------------------------
  // 2Dコース全体俯瞰トラック描画 (フル画面 or ワイプレーダー)
  // -------------------------------------------------------------------------
  function drawTopTrackOval(boxX, boxY, boxW, boxH, isMiniRadar) {{
    ctx.save();
    ctx.translate(boxX, boxY);

    // 背景パネル
    ctx.fillStyle = isMiniRadar ? "rgba(6, 78, 59, 0.88)" : "#064e3b";
    ctx.strokeStyle = "#eab308";
    ctx.lineWidth = isMiniRadar ? 1.5 : 2;
    ctx.beginPath();
    ctx.roundRect(0, 0, boxW, boxH, isMiniRadar ? 8 : 0);
    ctx.fill();
    if (isMiniRadar) ctx.stroke();

    const cx = boxW / 2;
    const cy = boxH / 2;
    const rx = boxW * 0.38;
    const ry = boxH * 0.34;
    const isDirt = course.surface === "ダート";
    const isRight = course.turn === "右";

    // トラック帯
    ctx.strokeStyle = isDirt ? "#b45309" : "#16a34a";
    ctx.lineWidth = isMiniRadar ? 16 : 38;
    ctx.beginPath();
    ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
    ctx.stroke();

    // 内外ラチ線
    ctx.strokeStyle = "#f8fafc";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.ellipse(cx, cy, rx - (isMiniRadar ? 8 : 19), ry - (isMiniRadar ? 8 : 19), 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.ellipse(cx, cy, rx + (isMiniRadar ? 8 : 19), ry + (isMiniRadar ? 8 : 19), 0, 0, Math.PI * 2);
    ctx.stroke();

    // 中央インフィールド文字
    ctx.fillStyle = "#fef08a";
    ctx.font = isMiniRadar ? "bold 10px sans-serif" : "bold 16px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(`${{course.venue}} ${{course.surface}}${{totalDist}}m (${{course.turn}})`, cx, cy - (isMiniRadar ? 2 : 6));
    if (!isMiniRadar) {{
      ctx.fillStyle = "#cbd5e1";
      ctx.font = "bold 13px sans-serif";
      ctx.fillText(`天候:${{course.weather}} / 馬場:${{course.condition}} / ${{paceType}}`, cx, cy + 16);
    }}

    // ゴール角度 (下側直線の中央右寄り or 左寄り)
    const goalAngle = Math.PI * 0.42;
    // 1周を約 1.45 * Math.PI ラジアン分使ってスタート位置からゴール角度まで回す
    const totalArc = Math.PI * 1.55;
    const dir = isRight ? 1 : -1;
    const startAngle = goalAngle - dir * totalArc;

    // ゴールラインマーカー
    const gx = cx + Math.cos(goalAngle) * rx;
    const gy = cy + Math.sin(goalAngle) * ry;
    ctx.fillStyle = "#ef4444";
    ctx.beginPath();
    ctx.arc(gx, gy, isMiniRadar ? 4 : 7, 0, Math.PI * 2);
    ctx.fill();

    // 各馬のプロット
    const nRunners = Math.max(1, runners.length);
    runners.forEach(r => {{
      const p = Math.min(1.0, r.dist / totalDist);
      const ang = startAngle + dir * (p * totalArc);
      const laneOffset = ((r.lateralY / nRunners) - 0.5) * (isMiniRadar ? 11 : 28);
      const hx = cx + Math.cos(ang) * (rx + laneOffset);
      const hy = cy + Math.sin(ang) * (ry + laneOffset);

      ctx.fillStyle = r.w_bg;
      ctx.strokeStyle = r.isSpurting ? "#38bdf8" : r.w_bd;
      ctx.lineWidth = r.isSpurting ? 2 : 1;
      ctx.beginPath();
      ctx.arc(hx, hy, isMiniRadar ? 5.5 : 10, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = r.w_fg;
      ctx.font = isMiniRadar ? "bold 7.5px sans-serif" : "bold 10px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(r.umaban), hx, hy);

      if (!isMiniRadar) {{
        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 10px sans-serif";
        ctx.fillText(r.name.slice(0, 5), hx, hy - 15);
      }}
    }});

    ctx.restore();
  }}

  // -------------------------------------------------------------------------
  // HUDオーバーレイ (レースタイトル・残り距離・時計・電光掲示板)
  // -------------------------------------------------------------------------
  function drawHudOverlay(W, H) {{
    let maxDist = 0;
    runners.forEach(r => {{ if (r.dist > maxDist) maxDist = r.dist; }});
    const remDist = Math.max(0, Math.round(totalDist - maxDist));

    // 左上 レース名＆残り距離プレート
    ctx.save();
    ctx.fillStyle = designMode === "tv" ? "rgba(12, 74, 110, 0.90)" : "rgba(15, 23, 42, 0.90)";
    ctx.strokeStyle = designMode === "tv" ? "#38bdf8" : "#eab308";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.roundRect(12, 10, 310, 56, 8);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#eab308";
    ctx.font = "bold 11px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(`${{course.venue}}${{course.race_num}}R｜${{course.surface}}${{totalDist}}m (${{course.turn}})｜天候:${{course.weather}} 馬場:${{course.condition}}`, 22, 27);

    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 15px sans-serif";
    ctx.fillText(course.race_name, 22, 48);

    // 残り距離＆タイムメーター
    ctx.fillStyle = remDist <= 400 ? "#dc2626" : "#1e293b";
    ctx.beginPath();
    ctx.roundRect(330, 10, 145, 56, 8);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#cbd5e1";
    ctx.font = "bold 10px sans-serif";
    ctx.fillText("残り距離 / タイム", 342, 26);
    ctx.fillStyle = "#fef08a";
    ctx.font = "bold 16px sans-serif";
    ctx.fillText(`${{remDist}}m`, 342, 49);
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 14px monospace";
    ctx.fillText(formatRaceTime(elapsedSimSec), 405, 49);

    // 待機中またはファンファーレ中のセンター案内バナー
    if (raceState === "ready") {{
      const bw = 380, bh = 54;
      const bx = (W - bw) / 2, by = H * 0.14;
      ctx.fillStyle = "rgba(15, 23, 42, 0.88)";
      ctx.strokeStyle = "#eab308";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.roundRect(bx, by, bw, bh, 10);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#fef08a";
      ctx.font = "bold 14px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("👆「🎺 ファンファーレ＆発走」または画面クリックで発走！", W / 2, by + 32);
    }} else if (raceState === "fanfare") {{
      const bw = 340, bh = 56;
      const bx = (W - bw) / 2, by = H * 0.14;
      ctx.fillStyle = "rgba(185, 28, 28, 0.92)";
      ctx.strokeStyle = "#fef08a";
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.roundRect(bx, by, bw, bh, 10);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 16px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("🎺 ファンファーレ演奏中… ゲートイン完了！", W / 2, by + 34);
    }}

    // ゴール確定時: 右側にJRA風 着順電光掲示板を表示
    if (raceState === "finished" && finishOrder.length > 0) {{
      const bx = W - 245;
      const by = 12;
      const bw = 232;
      const bh = 188;

      ctx.fillStyle = "rgba(9, 13, 22, 0.94)";
      ctx.strokeStyle = "#eab308";
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.roundRect(bx, by, bw, bh, 8);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = "#166534";
      ctx.fillRect(bx + 6, by + 6, bw - 12, 22);
      ctx.fillStyle = "#fef08a";
      ctx.font = "bold 11.5px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(`【確定】${{course.venue}} ${{course.race_num}}R 着順掲示板`, bx + bw / 2, by + 21);

      const top5 = finishOrder.slice(0, 5);
      const places = ["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ"];
      top5.forEach((r, i) => {{
        const ry = by + 36 + i * 24;
        ctx.fillStyle = "#1e293b";
        ctx.fillRect(bx + 8, ry, bw - 16, 20);

        ctx.fillStyle = "#fef08a";
        ctx.font = "bold 12px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(places[i], bx + 22, ry + 14);

        // 馬番ボックス
        ctx.fillStyle = r.w_bg;
        ctx.fillRect(bx + 36, ry + 2, 24, 16);
        ctx.fillStyle = r.w_fg;
        ctx.font = "bold 11px sans-serif";
        ctx.fillText(String(r.umaban), bx + 48, ry + 14);

        // 馬名
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "left";
        ctx.font = "bold 11px sans-serif";
        ctx.fillText(r.name.slice(0, 8), bx + 66, ry + 14);

        // 着差
        if (i > 0) {{
          const mTxt = formatMargin(r.finishTime - top5[i - 1].finishTime);
          ctx.fillStyle = "#38bdf8";
          ctx.textAlign = "right";
          ctx.font = "bold 10px sans-serif";
          ctx.fillText(mTxt, bx + bw - 12, ry + 14);
        }}
      }});

      // 勝ち時計＆上がり3F
      const winTime = formatRaceTime(top5[0].finishTime);
      const win3F = top5[0].last3FTime ? top5[0].last3FTime.toFixed(1) : "34.2";
      ctx.fillStyle = "#fef08a";
      ctx.textAlign = "left";
      ctx.font = "bold 11.5px monospace";
      ctx.fillText(`タイム ${{winTime}} / 上り3F ${{win3F}}`, bx + 14, by + bh - 10);
    }}

    ctx.restore();
  }}

  // -------------------------------------------------------------------------
  // メインアニメーションループ
  // -------------------------------------------------------------------------
  let prevTimeMs = performance.now();
  function loop(nowMs) {{
    const dtReal = Math.min(0.05, (nowMs - prevTimeMs) / 1000);
    prevTimeMs = nowMs;

    resizeCanvas();
    const W = canvas.width;
    const H = canvas.height;

    stepPhysics(dtReal);

    if (raceState === "running" && !paused) {{
      let anySpurt = runners.some(r => r.isSpurting && !r.finished);
      playHoofTick(nowMs, anySpurt);
      renderLiveTable(nowMs);
    }}

    // 視点モードごとの描画
    let maxDist = 0;
    runners.forEach(r => {{ if (r.dist > maxDist) maxDist = r.dist; }});
    const prog = maxDist / totalDist;

    if (viewMode === "top") {{
      drawTopTrackOval(0, 0, W, H, false);
    }} else if (viewMode === "side") {{
      drawSideView(W, H, prog >= 0.76);
    }} else {{
      // dynamic: サイドビュー + 直線ズーム + 右上(または右下)に2Dコース全体ミニレーダー
      drawSideView(W, H, prog >= 0.72);
      if (raceState !== "finished") {{
        const rw = Math.min(230, W * 0.32);
        const rh = Math.min(125, H * 0.30);
        drawTopTrackOval(W - rw - 12, 10, rw, rh, true);
      }}
    }}

    drawHudOverlay(W, H);
    requestAnimationFrame(loop);
  }}

  initRace(true);
  requestAnimationFrame(loop);
}})();
</script>
</body>
</html>
"""
    return html


def render_simulation_section(
    df: pd.DataFrame,
    meta_dict: Dict[str, Any],
    waku_style: Dict[int, Tuple[str, str, str]],
    cfg: Dict[str, Any],
    save_cfg_fn: Any,
    theme: Dict[str, Any],
) -> None:
    """
    app.py 内に直接組み込む『ウイニングポスト風 レースシミュレーション』セクションを描画する。
    - 取得データと能力パラメータの組み合わせ・重み付けをその場で変更・保存できる設定UI
    - 視点・デザイン切り替え対応のリアルタイム実況レースビューア
    - 100回モンテカルロシミュレーション集計表
    """
    st.subheader("🎬 ⑦ ウイニングポスト風 レースシミュレーション ＆ 能力連動システム")
    st.caption(
        "取得した8種類の指数・偏差値・獲得ポイントを各馬の4大能力（⚡スピード・🔥瞬発力・💪スタミナ・⚔️勝負根性）に連動させ、"
        "視点・デザイン切り替え可能な実況付きレースシミュレーションを行います。"
    )

    course = parse_course_details(meta_dict)

    # 保存済みの連動設定をロード（なければ推奨プリセット）
    default_preset_name = list(PARAM_MAPPING_PRESETS.keys())[0]
    saved_mapping = cfg.get("sim_param_mapping", PARAM_MAPPING_PRESETS[default_preset_name])

    # ------------------------------------------------------------------
    # 1. 取得データ × 能力パラメータ連動の組み合わせ変更UI
    # ------------------------------------------------------------------
    with st.expander("⚙️ 取得データと能力パラメータの連動設定（組み合わせ・重み変更・脚質調整）", expanded=False):
        st.markdown(
            "##### 🔗 1. 連動プリセット または カスタム組み合わせの選択\n"
            "どの取得データ（`UMA-X 4項目` / `Ω指数` / `無料競馬AI 2項目` / `keiba-ai着順予想` / `合計PT`）を"
            "どの能力パラメータに何％の重みで反映させるかをいつでも自由に変更・保存できます。"
        )

        preset_options = list(PARAM_MAPPING_PRESETS.keys()) + ["🎛️ カスタム（各能力の組み合わせを自由設定）"]
        cur_preset = cfg.get("sim_preset_name", default_preset_name)
        p_idx = preset_options.index(cur_preset) if cur_preset in preset_options else 0

        col_p1, col_p2, col_p3 = st.columns([2.4, 1.8, 1.3])
        with col_p1:
            selected_preset = st.selectbox("能力連動プリセット", preset_options, index=p_idx, key="sim_preset_sel")
        with col_p2:
            calc_source_map = {
                "ハイブリッド（元の指数値65% ＋ 獲得PT35%）": "hybrid",
                "元の指数・偏差値（生データ）のみ": "raw_only",
                "獲得ポイント（10〜0pt）のみ": "pt_only",
            }
            rev_calc_map = {v: k for k, v in calc_source_map.items()}
            active_base = (
                PARAM_MAPPING_PRESETS[selected_preset]
                if selected_preset in PARAM_MAPPING_PRESETS
                else saved_mapping
            )
            default_cs_label = rev_calc_map.get(active_base.get("calc_source", "hybrid"), list(calc_source_map.keys())[0])
            cs_label = st.selectbox(
                "計算元データの種類",
                list(calc_source_map.keys()),
                index=list(calc_source_map.keys()).index(default_cs_label),
                key="sim_calc_source_sel",
            )
        with col_p3:
            rand_val = st.slider(
                "展開の紛れ（ランダム性）",
                min_value=0.05,
                max_value=0.50,
                value=float(active_base.get("random_factor", 0.25)),
                step=0.05,
                help="小さくすると能力値通りの堅い決着になり、大きくすると展開のアヤや穴馬の激走が増えます。",
                key="sim_rand_slider",
            )

        # 各能力（スピード・瞬発力・スタミナ・勝負根性）ごとの連動項目＆重みスライダー
        st.markdown("##### 🎛️ 2. 各能力パラメータに連動させる取得データと重み（比率）")
        custom_weights: Dict[str, Dict[str, int]] = {}
        base_weights = active_base.get("weights", PARAM_MAPPING_PRESETS[default_preset_name]["weights"])

        ab_cols = st.columns(2)
        for idx_ab, ab in enumerate(ABILITY_PARAMS):
            ab_id = ab["id"]
            cur_w_dict = base_weights.get(ab_id, {})
            with ab_cols[idx_ab % 2]:
                st.markdown(f"**{ab['name']}**")
                st.caption(ab["desc"])
                default_labels = [METRIC_KEY_TO_LABEL[k] for k in cur_w_dict.keys() if k in METRIC_KEY_TO_LABEL]
                picked_labels = st.multiselect(
                    f"{ab['short']}に連動するデータ項目",
                    options=list(METRIC_LABEL_TO_KEY.keys()),
                    default=default_labels,
                    key=f"ms_{selected_preset}_{ab_id}",
                )
                w_for_ab: Dict[str, int] = {}
                if picked_labels:
                    w_cols = st.columns(len(picked_labels))
                    for i_l, lbl in enumerate(picked_labels):
                        m_key = METRIC_LABEL_TO_KEY[lbl]
                        init_w = int(cur_w_dict.get(m_key, 30))
                        with w_cols[i_l]:
                            w_v = st.number_input(
                                f"{m_key} 重み",
                                min_value=5,
                                max_value=100,
                                value=init_w,
                                step=5,
                                key=f"num_{selected_preset}_{ab_id}_{m_key}",
                            )
                            w_for_ab[m_key] = int(w_v)
                else:
                    w_for_ab = {"合計PT": 100}
                custom_weights[ab_id] = w_for_ab

        active_mapping = {
            "calc_source": calc_source_map[cs_label],
            "random_factor": float(rand_val),
            "weights": custom_weights,
        }

        if st.button("💾 この能力連動設定をデフォルトとして保存", use_container_width=True):
            cfg["sim_preset_name"] = selected_preset
            cfg["sim_param_mapping"] = active_mapping
            save_cfg_fn(cfg)
            st.success("能力パラメータ連動設定を保存しました！ 次回以降もこの組み合わせが自動適用されます。")

    # 能力パラメータ計算
    sim_df = compute_horse_simulation_stats(df, active_mapping)
    if sim_df.empty:
        st.warning("シミュレーション対象の出走馬データがありません。")
        return

    # 任意で脚質（逃・先・差・追）を手動変更できるミニ設定
    with st.expander("🐎 出走馬の脚質（逃・先・差・追）＆ 能力パラメータ一覧・手動調整", expanded=False):
        st.caption(
            "SP偏差値とAG偏差値のバランスから自動判定された各馬の脚質と4大能力パラメータ（50〜99）です。"
            "「もしこの馬が逃げたら？」などのテストをしたい場合は脚質を変更すると即座にシミュレーションへ反映されます。"
        )
        style_overrides: Dict[int, str] = {}
        s_cols = st.columns(min(4, max(1, len(sim_df))))
        for idx_h, (_, hrow) in enumerate(sim_df.sort_values("馬番").iterrows()):
            umaban = int(hrow["馬番"])
            cur_st = str(hrow["style"])
            st_opts = ["逃", "先", "差", "追"]
            with s_cols[idx_h % len(s_cols)]:
                picked_st = st.selectbox(
                    f"{umaban}番 {hrow['馬名']} (総合:{hrow['overall']})",
                    options=st_opts,
                    index=st_opts.index(cur_st) if cur_st in st_opts else 1,
                    key=f"style_ov_{meta_dict.get('race_id','')}_{umaban}",
                )
                style_overrides[umaban] = picked_st

        if style_overrides:
            sim_df = compute_horse_simulation_stats(df, active_mapping, style_overrides=style_overrides)

    # ------------------------------------------------------------------
    # 2. タブ構成: 🎬 1レース実況観戦ビューア / 📊 100回シミュレーション統計
    # ------------------------------------------------------------------
    tab_live, tab_mc = st.tabs(
        [
            "🎬 ウイニングポスト風 1レース実況観戦ビューア（視点・デザイン切替）",
            "📊 100回モンテカルロ・シミュレーション集計（勝率・連対率・期待値）",
        ]
    )

    with tab_live:
        viewer_html = build_winning_post_html(
            sim_df=sim_df,
            course=course,
            waku_style=waku_style,
            default_view="dynamic",
            default_design="wp",
            random_factor=float(active_mapping.get("random_factor", 0.25)),
        )
        components.html(viewer_html, height=795, scrolling=True)

    with tab_mc:
        st.markdown("##### 📊 展開・ペースの紛れを加味した100回レースシミュレーション集計")
        st.caption(
            "設定された能力パラメータ（⚡スピード・🔥瞬発力・💪スタミナ・⚔️勝負根性・脚質）をもとに、"
            "ペース変化や道中の位置取りの紛れを含めて100回レースを走らせた際の勝率・連対率・複勝率・単勝期待値です。"
        )
        mc_df = run_monte_carlo_simulations(
            sim_df=sim_df,
            course=course,
            n_trials=100,
            random_factor=float(active_mapping.get("random_factor", 0.25)),
        )
        show_cols = [
            "枠番",
            "馬番",
            "馬名",
            "騎手",
            "style",
            "合計_pt",
            "overall",
            "speed",
            "accel",
            "stamina",
            "guts",
            "シミュ勝率(%)",
            "シミュ連対率(%)",
            "シミュ複勝率(%)",
            "平均着順",
            "単勝オッズ",
            "単勝期待値",
        ]
        rename_map = {
            "style": "脚質",
            "合計_pt": "合計PT",
            "overall": "総合能力",
            "speed": "⚡SP",
            "accel": "🔥瞬発",
            "stamina": "💪スタミナ",
            "guts": "⚔️根性",
        }
        avail_mc_cols = [c for c in show_cols if c in mc_df.columns]
        st.dataframe(
            mc_df[avail_mc_cols].rename(columns=rename_map),
            use_container_width=True,
            hide_index=True,
        )
