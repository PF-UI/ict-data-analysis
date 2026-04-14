"""
合并 output 目录下爬虫导出的 .xlsx，按职位ID 去重并导出为一个文件。
默认跳过本脚本生成的历史文件（ict_jobs_deduped_*.xlsx），避免把去重结果再次并进去。
对「职位描述」「岗位职责」：合并重复 ID 时各字段只保留一条最佳文本（优先更长、非空），
并去除 BOSS / BOSS直聘 / 直聘 等爬虫常见干扰文案；若两段正文重复或一方为另一方子串，则只保留「职位描述」一条。
默认写出路径：job_recruit_crawler/ 目录下（而非 output/ 子目录）。
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import OUTPUT_DIR

# 本脚本默认写出到包根目录；爬虫原始表仍在 output/
PACKAGE_DIR = OUTPUT_DIR.parent
# 仅跳过本脚本命名的历史合并结果，不误伤其它含「deduped」字样的文件
_SKIP_MERGE_NAME_PREFIX = "ict_jobs_deduped_"


# 去除站点品牌与爬虫残留（顺序有意义：先长后短）
_BOSS_SUBSTRINGS = [
    "BOSS直聘",
    "Boss直聘",
    "boss直聘",
    "BOSS 直聘",
    "【BOSS直聘】",
    "[BOSS直聘]",
]

# 整行仅品牌等无意义内容时删行
_LINE_JUNK = re.compile(
    r"^\s*(BOSS|Boss|boss|直聘|BOSS直聘|Boss直聘|boss直聘)\s*$",
    re.MULTILINE,
)


def _strip_boss_noise(text: str) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    t = str(text)
    for s in _BOSS_SUBSTRINGS:
        t = t.replace(s, "")
    # 残余「直聘」常见于「上直聘」等引导语
    t = re.sub(r"上直聘|用直聘|下载\s*BOSS|打开\s*BOSS直聘", "", t, flags=re.IGNORECASE)
    t = re.sub(r"(?<![A-Za-z])BOSS(?![A-Za-z])", "", t, flags=re.IGNORECASE)
    # 孤立「直聘」（前后为标点或空白），避免误伤正常词时仅替换明显边界
    t = re.sub(r"(^|[\s，,。.；;：:])直聘($|[\s，,。.；;：:])", r"\1\2", t)
    t = _LINE_JUNK.sub("", t)
    t = re.sub(r"[ \t\r\f\v]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _normalize_compare(s: str) -> str:
    """比较用：压缩空白，忽略首尾"""
    if not s:
        return ""
    return re.sub(r"\s+", "", s)


def _best_text(candidates: list[str]) -> str:
    """取去噪后最长的非空串；都空则返回空"""
    cleaned = [_strip_boss_noise(c) for c in candidates]
    nonempty = [c for c in cleaned if c]
    if not nonempty:
        return ""
    return max(nonempty, key=len)


def _merge_desc_duty(desc: str, duty: str) -> tuple[str, str]:
    """
    若职位描述与岗位职责实质重复（相等或一方为另一方子串），只保留一条写入「职位描述」，
    「岗位职责」置空。
    """
    d = _strip_boss_noise(desc)
    r = _strip_boss_noise(duty)
    nd, nr = _normalize_compare(d), _normalize_compare(r)
    if not d:
        return r, ""
    if not r:
        return d, ""
    if nd == nr or (nd and nd in nr) or (nr and nr in nd):
        merged = d if len(d) >= len(r) else r
        return merged, ""
    return d, r


def _normalize_job_id(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s


def _first_nonempty(series: pd.Series):
    for v in series:
        if pd.isna(v):
            continue
        s = str(v).strip()
        if s:
            return v
    return series.iloc[0] if len(series) else ""


def dedupe_frames(frames: list[pd.DataFrame]) -> tuple[pd.DataFrame, dict]:
    if not frames:
        raise ValueError("没有可合并的表格")

    id_aliases = {"职位id", "职位Id", "job_id", "jobId", "id"}
    normalized: list[pd.DataFrame] = []
    for df in frames:
        d = df.copy()
        if "职位ID" not in d.columns:
            for a in id_aliases:
                if a in d.columns:
                    d = d.rename(columns={a: "职位ID"})
                    break
        normalized.append(d)

    all_cols: list[str] = []
    for d in normalized:
        all_cols.extend(d.columns.tolist())
    seen: set[str] = set()
    ordered_cols: list[str] = []
    for c in all_cols:
        if c not in seen:
            seen.add(c)
            ordered_cols.append(c)

    merged = pd.concat(
        [d.reindex(columns=ordered_cols) for d in normalized], ignore_index=True
    )

    if "职位ID" not in merged.columns:
        raise KeyError("合并结果中缺少「职位ID」列（或别名职位id）")

    merged["_norm_id"] = merged["职位ID"].map(_normalize_job_id)
    before = len(merged)
    merged = merged[merged["_norm_id"].astype(str).str.len() > 0].copy()
    dropped_empty = before - len(merged)

    text_cols = {"职位描述", "岗位职责"}
    exclude_merge = {"_norm_id"} | text_cols
    group_cols = [c for c in merged.columns if c not in exclude_merge]

    rows = []
    for nid, g in merged.groupby("_norm_id", sort=False):
        row: dict = {"职位ID": nid}
        for c in group_cols:
            if c == "职位ID":
                continue
            if c not in g.columns:
                continue
            row[c] = _first_nonempty(g[c])

        desc_best = _best_text(g["职位描述"].tolist() if "职位描述" in g else [])
        duty_best = _best_text(g["岗位职责"].tolist() if "岗位职责" in g else [])
        d, r = _merge_desc_duty(desc_best, duty_best)
        if "职位描述" in merged.columns:
            row["职位描述"] = d
        if "岗位职责" in merged.columns:
            row["岗位职责"] = r
        rows.append(row)

    out = pd.DataFrame(rows)
    # 列顺序：与合并表一致，缺的列补 NaN 再对齐
    for c in ordered_cols:
        if c != "职位ID" and c not in out.columns and c in merged.columns:
            out[c] = None
    # 职位ID 放首列
    front = ["职位ID"]
    rest = [c for c in ordered_cols if c != "职位ID" and c in out.columns]
    out = out[front + rest]

    meta = {
        "_dedupe_input_rows": before,
        "_dedupe_dropped_empty_id": dropped_empty,
        "_dedupe_output_rows": len(out),
    }
    return out, meta


def main():
    parser = argparse.ArgumentParser(description="output 下 Excel 按职位ID 去重合并")
    parser.add_argument(
        "--dir",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Excel 所在目录（默认: {OUTPUT_DIR}）",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=f"输出 .xlsx 路径；默认写入 {PACKAGE_DIR}\\ict_jobs_deduped_<时间戳>.xlsx",
    )
    parser.add_argument(
        "--include-deduped",
        action="store_true",
        help="同时读取 output 内已生成的 ict_jobs_deduped_*.xlsx（一般不必，再去重一次与源表合并等价）",
    )
    args = parser.parse_args()
    out_dir = args.dir.resolve()
    if not out_dir.is_dir():
        raise SystemExit(f"目录不存在: {out_dir}")

    raw = sorted(out_dir.glob("*.xlsx"), key=lambda p: p.name.lower())
    skipped_prev: list[Path] = []
    paths: list[Path] = []
    seen_resolved: set[Path] = set()
    for p in raw:
        if p.name.startswith("~$"):
            continue
        if (
            not args.include_deduped
            and p.name.startswith(_SKIP_MERGE_NAME_PREFIX)
            and p.suffix.lower() == ".xlsx"
        ):
            skipped_prev.append(p)
            continue
        key = p.resolve()
        if key in seen_resolved:
            continue
        seen_resolved.add(key)
        paths.append(p)

    if not paths:
        raise SystemExit(f"未找到 xlsx 文件: {out_dir}")

    frames = [pd.read_excel(p, engine="openpyxl") for p in paths]
    result, meta = dedupe_frames(frames)

    out_path = args.output
    if out_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
        out_path = PACKAGE_DIR / f"ict_jobs_deduped_{ts}.xlsx"
    else:
        out_path = out_path.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

    result.to_excel(out_path, index=False, engine="openpyxl")
    print(f"读取源表: {len(paths)} 个")
    for p in paths:
        print(f"  - {p.name}")
    if skipped_prev:
        print(f"跳过历史合并文件: {len(skipped_prev)} 个（可用 --include-deduped 一并读入）")
        for p in skipped_prev:
            print(f"  (跳过) {p.name}")
    print(f"合并前行数: {meta['_dedupe_input_rows']}（空职位ID 丢弃 {meta['_dedupe_dropped_empty_id']}）")
    print(f"去重后行数: {meta['_dedupe_output_rows']}")
    print(f"已写入: {out_path}")


if __name__ == "__main__":
    main()
