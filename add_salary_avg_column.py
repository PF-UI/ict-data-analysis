#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
独立脚本：为 job_listings 表添加平均薪资字段并批量更新数据

使用方法：
    python add_salary_avg_column.py

功能：
    1. 检查并添加 salary_avg 字段（如果不存在）
    2. 解析所有记录的 salary_range 字段
    3. 批量更新平均薪资数据
"""

import sys
import re
import math
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_salary(salary_str):
    """
    解析薪资格式，将各种格式的薪资转换为月薪数值
    :param salary_str: 薪资格式字符串
    :return: 月薪数值（整数）或 None（无法解析时）
    """
    # 空值处理
    if salary_str is None:
        return None
    
    if isinstance(salary_str, float) and math.isnan(salary_str):
        return None
    
    salary_str = str(salary_str).strip()
    if salary_str == 'nan' or salary_str == "":
        return None

    # 预设参数
    work_days_per_month = 21.75  # 月平均工作日
    work_hours_per_day = 8  # 每日工作时长

    # 处理 "面议" 的情况
    if salary_str == "面议":
        return None

    # 解析优先级从高到低排列

    # 1. 处理时薪（如"21元/小时"）
    if '元/小时' in salary_str:
        if match := re.match(r'(\d+\.?\d*)元/小时', salary_str):
            hourly = float(match.group(1))
            monthly = hourly * work_hours_per_day * work_days_per_month
            return int(round(monthly))

    # 处理新的时薪格式（如 "10-25元/时" 和单个金额的 "300元/时"）
    if '元/时' in salary_str:
        if re.search(r'(\d+\.?\d*)-(\d+\.?\d*)元/时', salary_str):
            match = re.match(r'(\d+\.?\d*)-(\d+\.?\d*)元/时', salary_str)
            lower = float(match.group(1))
            upper = float(match.group(2))
            monthly = (lower + upper) / 2 * work_hours_per_day * work_days_per_month
            return int(round(monthly))
        elif match := re.match(r'(\d+\.?\d*)元/时', salary_str):
            hourly = float(match.group(1))
            monthly = hourly * work_hours_per_day * work_days_per_month
            return int(round(monthly))

    # 2. 处理日薪（如"200元/天"）
    if '元/天' in salary_str:
        if match := re.match(r'(\d+\.?\d*)元/天', salary_str):
            daily = float(match.group(1))
            return int(round(daily * work_days_per_month))

    # 处理新的日薪格式（如 "60-100元/天"、"150-200元/天" 等）
    if re.search(r'\d+-\d+元/天', salary_str):
        if match := re.match(r'(\d+\.?\d*)-(\d+\.?\d*)元/天', salary_str):
            lower = float(match.group(1))
            upper = float(match.group(2))
            return int(round((lower + upper) / 2 * work_days_per_month))

    # 3. 处理特殊月薪（如"10万以上/月"）
    if '以上/月' in salary_str:
        if match := re.match(r'(\d+\.?\d*)(万|千)以上/月', salary_str):
            value, unit = match.groups()
            multiplier = 10000 if unit == '万' else 1000
            return int(round(float(value) * multiplier))

    # 处理特殊年薪（如"100万以上/年"）
    if '以上/年' in salary_str:
        if match := re.match(r'(\d+\.?\d*)(万|千)以上/年', salary_str):
            value, unit = match.groups()
            multiplier = 10000 if unit == '万' else 1000
            return int(round(float(value) * multiplier / 12))

    # 4. 处理带年终奖的复合格式（如"1.5-2.5万·13薪"）
    if '·' in salary_str:
        parts = salary_str.split('·')
        if len(parts) == 2 and '薪' in parts[1]:
            main_salary = parse_salary(parts[0])
            if main_salary is not None:
                if bonus_match := re.match(r'(\d+)薪', parts[1]):
                    return int(round(main_salary * int(bonus_match.group(1)) / 12))

    # 处理新的带年终奖且单位为元的格式（如 "8000-16000元·13薪"）
    if re.search(r'\d+-\d+元·\d+薪', salary_str):
        parts = salary_str.split('·')
        if len(parts) == 2 and '薪' in parts[1]:
            if match := re.match(r'(\d+)-(\d+)元', parts[0]):
                lower = float(match.group(1))
                upper = float(match.group(2))
                main_salary = (lower + upper) / 2
                if bonus_match := re.match(r'(\d+)薪', parts[1]):
                    return int(round(main_salary * int(bonus_match.group(1)) / 12))

    # 5. 处理带时间单位的范围薪资（如"1.1-1.8万/月"）
    range_pattern_month = r'''
        ^
        ([\d.]+)    # 起始值
        -
        ([\d.]+)    # 结束值
        (万|千)     # 单位
        /月
    '''
    if match := re.match(range_pattern_month, salary_str, re.VERBOSE):
        lower, upper, unit = match.groups()
        multiplier = 10000 if unit == '万' else 1000
        return int(round((float(lower) * multiplier + float(upper) * multiplier) / 2))

    # 处理新的月薪格式（如 "10000-15000元/月"）
    if re.search(r'\d+-\d+元/月', salary_str):
        if match := re.match(r'(\d+)-(\d+)元/月', salary_str):
            lower = float(match.group(1))
            upper = float(match.group(2))
            return int(round((lower + upper) / 2))

    # 处理无时间单位且单位为元的薪资范围（如 "6000-10000元"）
    if re.search(r'\d+-\d+元', salary_str):
        if match := re.match(r'(\d+)-(\d+)元', salary_str):
            lower = float(match.group(1))
            upper = float(match.group(2))
            return int(round((lower + upper) / 2))

    # 处理固定金额的薪资，单位为"元"或"万"（如 "1万"、"5000元"）
    if re.search(r'\d+万', salary_str):
        if match := re.match(r'(\d+)万', salary_str):
            value = float(match.group(1))
            return int(round(value * 10000))
    elif re.search(r'\d+元', salary_str):
        if match := re.match(r'(\d+)元', salary_str):
            return int(round(float(match.group(1))))

    # 处理带有上下限描述的固定金额薪资（如 "1000元以下"）
    if re.search(r'\d+元(以下|以上)', salary_str):
        if match := re.match(r'(\d+)元(以下|以上)', salary_str):
            value = float(match.group(1))
            direction = match.group(2)
            if direction == "以下":
                return int(round(value * 0.8))
            elif direction == "以上":
                return int(round(value * 1.2))

    # 6. 处理按年计算的范围薪资（如 "15-25万/年"）
    range_pattern_year = r'''
        ^
        ([\d.]+)    # 起始值
        -
        ([\d.]+)    # 结束值
        (万|千)     # 单位
        /年
    '''
    if match := re.match(range_pattern_year, salary_str, re.VERBOSE):
        lower, upper, unit = match.groups()
        multiplier = 10000 if unit == '万' else 1000
        return int(round((float(lower) * multiplier + float(upper) * multiplier) / 12))

    # 7. 处理无时间单位的范围薪资（如"1.5-3万"）
    range_pattern_no_time = r'''
        ^
        ([\d.]+)    # 起始值
        -
        ([\d.]+)    # 结束值
        (万|千)     # 单位
        (?!/)       # 排除有时间单位的情况
    '''
    if match := re.match(range_pattern_no_time, salary_str, re.VERBOSE):
        lower, upper, unit = match.groups()
        multiplier = 10000 if unit == '万' else 1000
        return int(round((float(lower) * multiplier + float(upper) * multiplier) / 2))

    # 处理以K为单位的薪资范围（如 "3-4K"）
    k_range_pattern = r'^(\d+\.?\d*)-(\d+\.?\d*)K$'
    if match := re.match(k_range_pattern, salary_str):
        lower = float(match.group(1)) * 1000
        upper = float(match.group(2)) * 1000
        return int(round((lower + upper) / 2))

    # 处理不同单位的范围薪资（如 "8千 - 1.6万"）
    diff_unit_range_pattern = r'^(\d+\.?\d*)(千)-(\d+\.?\d*)(万)$'
    if match := re.match(diff_unit_range_pattern, salary_str):
        lower = float(match.group(1)) * 1000
        upper = float(match.group(3)) * 10000
        return int(round((lower + upper) / 2))

    # 8. 处理上下限薪资（如"1.5千以下/月"）
    limit_pattern = r'''
        ^
        ([\d.]+)    # 数值
        (万|千)     # 单位
        (以下|以上)  # 限定方向
        /月
    '''
    if match := re.match(limit_pattern, salary_str, re.VERBOSE):
        value, unit, direction = match.groups()
        multiplier = 10000 if unit == '万' else 1000
        base = float(value) * multiplier
        # 根据方向调整估值
        return int(round(base * (0.8 if direction == '以下' else 1.2)))

    logger.warning(f"无法识别的薪资格式: {salary_str}")
    return None


def check_column_exists(engine, table_name, column_name):
    """检查表中是否存在指定列"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def add_salary_avg_column(engine):
    """添加 salary_avg 字段到 job_listings 表"""
    table_name = "job_listings"
    column_name = "salary_avg"
    
    if check_column_exists(engine, table_name, column_name):
        logger.info(f"✅ 字段 {column_name} 已存在，跳过添加")
        return True
    
    try:
        with engine.connect() as conn:
            # 添加字段（允许 NULL，后续会更新）
            alter_sql = text(f"""
                ALTER TABLE {table_name} 
                ADD COLUMN {column_name} INT NULL COMMENT '平均月薪（元）'
            """)
            conn.execute(alter_sql)
            conn.commit()
            
            # 为字段添加索引（可选，但有助于查询性能）
            try:
                index_sql = text(f"""
                    CREATE INDEX idx_salary_avg ON {table_name}({column_name})
                """)
                conn.execute(index_sql)
                conn.commit()
                logger.info(f"✅ 已为 {column_name} 字段创建索引")
            except Exception as e:
                logger.warning(f"⚠️ 创建索引失败（可能已存在）: {e}")
            
            logger.info(f"✅ 成功添加字段 {column_name}")
            return True
    except Exception as e:
        logger.error(f"❌ 添加字段失败: {e}")
        return False


def update_salary_data(engine, batch_size=100):
    """批量更新薪资数据"""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        # 获取所有有薪资范围但还没有平均薪资的记录
        query = text("""
            SELECT id, salary_range 
            FROM job_listings 
            WHERE salary_range IS NOT NULL 
            AND (salary_avg IS NULL OR salary_avg = 0)
        """)
        
        result = session.execute(query)
        records = result.fetchall()
        total = len(records)
        
        if total == 0:
            logger.info("✅ 所有记录的薪资数据已是最新，无需更新")
            return
        
        logger.info(f"📊 找到 {total} 条需要更新的记录")
        
        updated = 0
        failed = 0
        failed_records = []  # 收集失败记录用于报告
        
        # 批量处理
        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]
            batch_updates = []
            
            for record in batch:
                job_id, salary_range = record
                salary_avg = parse_salary(salary_range)
                
                if salary_avg is not None:
                    batch_updates.append({
                        'id': job_id,
                        'salary_avg': salary_avg
                    })
                else:
                    failed += 1
                    failed_records.append({
                        'id': job_id,
                        'salary_range': salary_range
                    })
                    logger.debug(f"⚠️ ID {job_id} 的薪资格式无法解析: {salary_range}")
            
            # 批量更新
            if batch_updates:
                update_query = text("""
                    UPDATE job_listings 
                    SET salary_avg = :salary_avg 
                    WHERE id = :id
                """)
                
                session.execute(update_query, batch_updates)
                session.commit()
                updated += len(batch_updates)
                
                logger.info(f"📝 已处理 {min(i + batch_size, total)}/{total} 条记录 "
                          f"(成功: {updated}, 失败: {failed})")
        
        logger.info(f"✅ 批量更新完成！成功: {updated} 条, 失败: {failed} 条")
        
        # 输出失败记录统计
        if failed_records:
            logger.info(f"\n📋 失败记录统计（共 {failed} 条）:")
            # 统计失败的薪资格式类型
            failed_patterns = {}
            for record in failed_records:
                pattern = record['salary_range'] or 'NULL'
                failed_patterns[pattern] = failed_patterns.get(pattern, 0) + 1
            
            # 按出现次数排序，显示前20个最常见的失败格式
            sorted_patterns = sorted(failed_patterns.items(), key=lambda x: x[1], reverse=True)
            logger.info(f"   最常见的无法解析的薪资格式（前20个）:")
            for i, (pattern, count) in enumerate(sorted_patterns[:20], 1):
                logger.info(f"   {i:2d}. {pattern} (出现 {count} 次)")
            
            if len(sorted_patterns) > 20:
                logger.info(f"   ... 还有 {len(sorted_patterns) - 20} 种其他格式")
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 更新数据失败: {e}")
        raise
    finally:
        session.close()


def main():
    """主函数"""
    logger.info("🚀 开始执行薪资字段添加和数据更新脚本")
    
    try:
        # 创建数据库引擎
        database_url = settings.DATABASE_URL
        logger.info(f"📌 数据库连接: {database_url.split('@')[1] if '@' in database_url else 'N/A'}")
        
        engine = create_engine(database_url, echo=False)
        
        # 测试连接
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ 数据库连接成功")
        
        # 步骤1: 添加字段
        logger.info("\n" + "="*50)
        logger.info("步骤 1: 检查并添加 salary_avg 字段")
        logger.info("="*50)
        if not add_salary_avg_column(engine):
            logger.error("❌ 添加字段失败，脚本终止")
            return
        
        # 步骤2: 更新数据
        logger.info("\n" + "="*50)
        logger.info("步骤 2: 批量更新薪资数据")
        logger.info("="*50)
        update_salary_data(engine)
        
        logger.info("\n" + "="*50)
        logger.info("✅ 脚本执行完成！")
        logger.info("="*50)
        
    except Exception as e:
        logger.error(f"❌ 脚本执行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()

