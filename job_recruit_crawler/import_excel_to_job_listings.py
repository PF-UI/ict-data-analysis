# -*- coding: utf-8 -*-
"""
将爬虫导出的 Excel 写入 MySQL `job_listings` 表。

约定（与当前项目模型 app.models.job_listing.JobListing 一致）：
- id：自增，插入时不指定
- location：Excel「城市」列（只到市）
- openings：固定 1
- requirements：Excel「职位描述」
- created_at：本条记录插入时的当前时间（不使用 Excel「创建时间」）
- salary_avg：插入 NULL，可后续用项目根目录 add_salary_avg_column.py 批量计算

依赖：在项目根目录执行，已配置 .env 中 DATABASE_URL；需安装 sqlalchemy、pymysql、pandas、openpyxl。

用法（二选一）：
  在项目根目录：
    cd C:\\recruitment_kg
    python job_recruit_crawler/import_excel_to_job_listings.py
  在本脚本所在目录时不要再写 job_recruit_crawler/ 前缀：
    cd C:\\recruitment_kg\\job_recruit_crawler
    python import_excel_to_job_listings.py
    python import_excel_to_job_listings.py -f ict_jobs_deduped_20260403_230946_textmerged.xlsx --dry-run
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.job_listing import JobListing

# Excel 列名（与 boss 爬虫导出一致）
COL_TITLE = "岗位名称"
COL_COMPANY = "公司名称"
COL_SALARY = "薪资范围"
COL_CITY = "城市"
COL_DESC = "职位描述"
COL_KEYWORD = "搜索关键词"
COL_YEAR = "数据年份"


def _s(val, max_len: int | None = None) -> str | None:
    if val is None or (isinstance(val, float) and (math.isnan(val) or pd.isna(val))):
        return None
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    if max_len is not None and len(s) > max_len:
        return s[:max_len]
    return s


def _year(val) -> int | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def import_rows(session: Session, df: pd.DataFrame) -> int:
    now = datetime.now().replace(microsecond=0)
    batch: list[JobListing] = []
    n = 0
    for _, row in df.iterrows():
        title = _s(row.get(COL_TITLE), 250) or "未知"
        company = _s(row.get(COL_COMPANY), 250) or "未知"
        jl = JobListing(
            job_title=title,
            company_name=company,
            salary_range=_s(row.get(COL_SALARY), 100),
            salary_avg=None,
            location=_s(row.get(COL_CITY), 100),
            openings=1,
            requirements=_s(row.get(COL_DESC)) or None,
            search_keyword=_s(row.get(COL_KEYWORD), 100),
            data_year=_year(row.get(COL_YEAR)),
            created_at=now,
        )
        batch.append(jl)
        n += 1
        if len(batch) >= 500:
            session.add_all(batch)
            session.commit()
            batch.clear()
    if batch:
        session.add_all(batch)
        session.commit()
    return n


def main():
    parser = argparse.ArgumentParser(description="Excel 导入 job_listings")
    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        default=_ROOT
        / "job_recruit_crawler"
        / "ict_jobs_deduped_20260403_230946_textmerged.xlsx",
        help="xlsx 路径",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只解析并打印行数，不写库",
    )
    args = parser.parse_args()
    path = args.file.resolve()
    if not path.is_file():
        raise SystemExit(f"文件不存在: {path}")

    df = pd.read_excel(path, engine="openpyxl")
    required = [COL_TITLE, COL_COMPANY, COL_CITY, COL_DESC, COL_KEYWORD, COL_YEAR]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"缺少列: {missing}，当前列: {list(df.columns)}")

    print(f"读取 {len(df)} 行: {path}")
    if args.dry_run:
        print("dry-run：未写入数据库")
        return

    db = SessionLocal()
    try:
        count = import_rows(db, df)
        print(f"已提交 {count} 条到 job_listings（salary_avg 为 NULL，created_at 为导入时刻）")
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
