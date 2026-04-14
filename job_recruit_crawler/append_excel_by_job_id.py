"""
将「追加」Excel 并入「目标」Excel，按职位ID 去重后写出。
同一职位ID 保留目标文件中已有行（先目标后追加）。
写入方式与 merge_job_text_fields.py 一致：openpyxl、写出前 mkdir、默认同目录命名。
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

_COL_ID = "职位ID"
_PACKAGE = Path(__file__).resolve().parent


def _normalize_job_id(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s


def merge_append_frames(target: Path, extra: Path) -> tuple[pd.DataFrame, dict]:
    df_t = pd.read_excel(target, engine="openpyxl")
    df_e = pd.read_excel(extra, engine="openpyxl")

    if _COL_ID not in df_t.columns or _COL_ID not in df_e.columns:
        raise KeyError(f"两个表均需包含「{_COL_ID}」列")

    before_t, before_e = len(df_t), len(df_e)
    df_t = df_t.copy()
    df_e = df_e.copy()
    df_t["_norm_id"] = df_t[_COL_ID].map(_normalize_job_id)
    df_e["_norm_id"] = df_e[_COL_ID].map(_normalize_job_id)

    dropped_t = int((df_t["_norm_id"].astype(str).str.len() == 0).sum())
    dropped_e = int((df_e["_norm_id"].astype(str).str.len() == 0).sum())
    df_t = df_t[df_t["_norm_id"].astype(str).str.len() > 0]
    df_e = df_e[df_e["_norm_id"].astype(str).str.len() > 0]

    merged = pd.concat([df_t, df_e], ignore_index=True)
    dup_before = len(merged)
    merged = merged.drop_duplicates(subset=["_norm_id"], keep="first")
    merged = merged.drop(columns=["_norm_id"])

    meta = {
        "target_rows": before_t,
        "extra_rows": before_e,
        "dropped_empty_id_target": dropped_t,
        "dropped_empty_id_extra": dropped_e,
        "merged_rows": len(merged),
        "duplicates_removed": dup_before - len(merged),
    }
    return merged, meta


def main():
    parser = argparse.ArgumentParser(description="追加 Excel 并按职位ID 去重写出")
    parser.add_argument(
        "target",
        type=Path,
        nargs="?",
        default=_PACKAGE / "ict_jobs_deduped_20260403_230946_textmerged.xlsx",
        help="目标 xlsx（重复 ID 时保留此表中的行）",
    )
    parser.add_argument(
        "extra",
        type=Path,
        nargs="?",
        default=_PACKAGE / "ict_jobs_deduped_20260404_204328.xlsx",
        help="要并入的 xlsx",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="输出路径；默认同目录 <目标 stem>_appended.xlsx",
    )
    args = parser.parse_args()
    target = args.target.resolve()
    extra = args.extra.resolve()
    if not target.is_file():
        raise SystemExit(f"文件不存在: {target}")
    if not extra.is_file():
        raise SystemExit(f"文件不存在: {extra}")

    out_df, meta = merge_append_frames(target, extra)

    out_path = args.output
    if out_path is None:
        out_path = target.parent / f"{target.stem}_appended.xlsx"
    else:
        out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_excel(out_path, index=False, engine="openpyxl")

    print(f"行数: {len(out_df)}")
    print(f"已写入: {out_path}")
    print(
        f"（目标 {meta['target_rows']} 行 + 追加 {meta['extra_rows']} 行，"
        f"空{_COL_ID} 丢弃 {meta['dropped_empty_id_target']}+{meta['dropped_empty_id_extra']}，"
        f"重复 ID 删 {meta['duplicates_removed']}）"
    )


if __name__ == "__main__":
    main()
