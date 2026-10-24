"""
指定開催日（デフォルトは直近の土日）の全レースの指数データ（UMA-X / 競馬ラボ / 無料競馬AI / keiba-ai.jp）を
日本の回線から一括高速取得し、race_cache.json に保存するスクリプト。
"""

import concurrent.futures
import sys
import time
from typing import Dict, List

from scraper import KeibaScraper, RaceMeta, load_all_cache, save_all_cache

sys.stdout.reconfigure(encoding="utf-8")


def fetch_single_race_indices(meta: RaceMeta) -> tuple[str, dict]:
    s = KeibaScraper(timeout=10)
    entry = {}

    umax_data, st_umax = s.fetch_umax(meta)
    if st_umax.success and umax_data:
        entry["umax"] = {str(k): v for k, v in umax_data.items()}

    omega_data, st_klab = s.fetch_keibalab_omega(meta)
    if st_klab.success and omega_data:
        entry["omega"] = {str(k): v for k, v in omega_data.items()}

    origin_data, wave_data, st_mai = s.fetch_muryou_ai(meta)
    if st_mai.success and (origin_data or wave_data):
        entry["origin"] = {str(k): v for k, v in origin_data.items()}
        entry["wave"] = {str(k): v for k, v in wave_data.items()}
        entry["muryou_url"] = st_mai.url

    athena_ranks, athena_ai_str, st_kai = s.fetch_keiba_ai(meta)
    if st_kai.success and athena_ranks:
        entry["athena_ranks"] = {str(k): v for k, v in athena_ranks.items()}
        entry["athena_ai_str"] = {str(k): v for k, v in athena_ai_str.items()}

    return meta.race_id, entry


def prefetch_dates(dates: List[str]) -> int:
    scraper = KeibaScraper()
    all_cache = load_all_cache()
    all_metas: List[RaceMeta] = []

    for d in dates:
        races = scraper.get_races_for_date(d)
        print(f"開催日 {d}: {len(races)} レース検出")
        all_metas.extend(races)

    print(f"合計 {len(all_metas)} レースの指数データを並列取得中...")
    done_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_to_meta = {executor.submit(fetch_single_race_indices, m): m for m in all_metas}
        for future in concurrent.futures.as_completed(future_to_meta):
            m = future_to_meta[future]
            try:
                rid, entry = future.result()
                if entry:
                    all_cache[rid] = entry
                done_count += 1
                print(
                    f"  [{done_count}/{len(all_metas)}] {m.kaisai_date} {m.venue_name}{m.race_num}R "
                    f"(UMA:{'○' if 'umax' in entry else '-'} Ω:{'○' if 'omega' in entry else '-'} "
                    f"無料AI:{'○' if 'origin' in entry else '-'} ATHENA:{'○' if 'athena_ranks' in entry else '-'})"
                )
            except Exception as e:
                print(f"  [ERROR] {m.race_id}: {e}")

    save_all_cache(all_cache)
    print(f"\n完了！ {len(all_cache)} レース分のキャッシュを race_cache.json に保存しました。")
    return len(all_cache)


if __name__ == "__main__":
    target_dates = sys.argv[1:] if len(sys.argv) > 1 else ["20261024", "20261025"]
    prefetch_dates(target_dates)
