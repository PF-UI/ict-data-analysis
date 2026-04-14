"""
将 Excel 中「职位描述 / 岗位职责 / 任职要求」合并到「职位描述」一列，
并去除 kanzhun 相关爬虫噪音（域名、独立词等）。合并时按顺序去重：
若某一整段在去空白后与另一段相同或是对方子串，只保留较长/靠前的一段。
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


_COL_DESC = "职位描述"
_COL_DUTY = "岗位职责"
_COL_REQ = "任职要求"


def _normalize_compare(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", "", str(s))


def _strip_kanzhun(text: str | float) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    t = str(text)
    t = re.sub(r"https?://[^\s)\]\"']*kanzhun[^\s)\]\"']*", "", t, flags=re.IGNORECASE)
    t = re.sub(
        r"[a-z0-9.-]*kanzhun[a-z0-9./?#&=%-]*",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"\bkanzhun\b", "", t, flags=re.IGNORECASE)
    t = t.replace("kanzhun", "").replace("Kanzhun", "").replace("KANZHUN", "")
    t = re.sub(r"[ \t\r\f\v]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _drop_substring_blocks_ordered(blocks: list[str]) -> list[str]:
    """保留顺序；若某块在去空白后是另一块的子串（且不相等时较短被删），去掉较短/后出现的冗余。"""
    raw = [b for b in blocks if b and str(b).strip()]
    if len(raw) <= 1:
        return raw
    norms = [_normalize_compare(b) for b in raw]
    keep_idx: list[int] = []
    for i, ni in enumerate(norms):
        if not ni:
            continue
        is_sub_of_other = False
        for j, nj in enumerate(norms):
            if i == j or not nj:
                continue
            if ni != nj and ni in nj:
                is_sub_of_other = True
                break
        if not is_sub_of_other:
            keep_idx.append(i)
    # 同长重复只保留第一次
    seen: set[str] = set()
    out: list[str] = []
    for i in keep_idx:
        ni = norms[i]
        if ni in seen:
            continue
        seen.add(ni)
        out.append(raw[i])
    return out


def merge_three_fields(desc, duty, req) -> tuple[str, str, str]:
    d = _strip_kanzhun(desc)
    u = _strip_kanzhun(duty)
    r = _strip_kanzhun(req)
    merged = "\n\n".join(_drop_substring_blocks_ordered([d, u, r]))
    return merged, "", ""


def main():
    parser = argparse.ArgumentParser(description="合并职位描述三列并去除 kanzhun 噪音")
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parent
        / "ict_jobs_deduped_20260403_230946.xlsx",
        help="输入 xlsx",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="输出路径；默认同目录 < stem >_textmerged.xlsx",
    )
    args = parser.parse_args()
    inp = args.input.resolve()
    if not inp.is_file():
        raise SystemExit(f"文件不存在: {inp}")

    df = pd.read_excel(inp, engine="openpyxl")
    for c in (_COL_DESC, _COL_DUTY, _COL_REQ):
        if c not in df.columns:
            raise SystemExit(f"缺少列「{c}」，当前列: {list(df.columns)}")

    merged_desc = []
    merged_duty = []
    merged_req = []
    for _, row in df.iterrows():
        a, b, c = merge_three_fields(
            row[_COL_DESC], row[_COL_DUTY], row[_COL_REQ]
        )
        merged_desc.append(a)
        merged_duty.append(b)
        merged_req.append(c)

    out_df = df.copy()
    out_df[_COL_DESC] = merged_desc
    out_df[_COL_DUTY] = merged_duty
    out_df[_COL_REQ] = merged_req

    out_path = args.output
    if out_path is None:
        out_path = inp.parent / f"{inp.stem}_textmerged.xlsx"
    else:
        out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_excel(out_path, index=False, engine="openpyxl")
    print(f"行数: {len(out_df)}")
    print(f"已写入: {out_path}")


if __name__ == "__main__":
    main()
