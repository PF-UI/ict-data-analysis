"""
检查 job_listings 表中的 location 字段是否在 city_mapping 映射表中有对应映射
"""
from collections import Counter
from typing import Tuple
from app.database import SessionLocal
from app.models.job_listing import JobListing
from app.models.city_mapping import CityMapping


def extract_city_name(location: str) -> str:
    """
    从 location 中提取城市名
    处理格式如 "武汉-江夏区"、"北京"、"上海" 等
    """
    if not location:
        return ""
    
    location = location.strip()
    # 提取城市名（第一个"-"前的部分，去掉"市"字）
    city_name = location.split('-')[0].split('市')[0].strip()
    return city_name


def check_location_mapping(location: str, city_map: dict) -> Tuple[bool, str]:
    """
    检查 location 是否能在映射表中找到匹配
    
    Returns:
        (是否匹配, 匹配的省份名称或None)
    """
    if not location:
        return False, None
    
    location = location.strip()
    city_name = extract_city_name(location)
    
    # 首先尝试完整匹配
    if city_name in city_map:
        return True, city_map[city_name]
    
    # 尝试部分匹配（映射表中的简称）
    for short_name, full_name in city_map.items():
        # 检查映射表的简称是否在地点中
        if short_name in location or location.startswith(short_name):
            return True, full_name
        # 检查地点是否在映射表的简称中（如"武汉"匹配"武汉"）
        if city_name in short_name or short_name in city_name:
            return True, full_name
    
    return False, None


def check_all_locations():
    """
    检查所有 job_listings 中的 location 是否在映射表中有对应
    """
    db = SessionLocal()
    try:
        # 获取所有城市映射
        city_mappings = db.query(CityMapping).all()
        city_map = {mapping.short_name: mapping.full_name for mapping in city_mappings}
        
        print(f"📊 映射表中共有 {len(city_map)} 个城市映射\n")
        
        # 获取所有唯一的 location 值
        locations = db.query(JobListing.location).distinct().all()
        locations = [loc[0] for loc in locations if loc[0]]  # 过滤掉 None
        
        print(f"📋 job_listings 表中共有 {len(locations)} 个不同的 location 值\n")
        
        # 统计每个 location 出现的次数
        location_counts = db.query(
            JobListing.location,
            db.query(JobListing).filter(JobListing.location == JobListing.location).count()
        ).distinct().all()
        
        # 重新统计（上面的查询不对，应该用 group_by）
        from sqlalchemy import func
        location_counts = db.query(
            JobListing.location,
            func.count(JobListing.id).label('count')
        ).filter(JobListing.location.isnot(None)).group_by(JobListing.location).all()
        
        location_count_dict = {loc: count for loc, count in location_counts}
        
        # 检查每个 location
        matched = []
        unmatched = []
        
        for location in locations:
            is_matched, province = check_location_mapping(location, city_map)
            count = location_count_dict.get(location, 0)
            
            if is_matched:
                matched.append({
                    'location': location,
                    'count': count,
                    'province': province
                })
            else:
                unmatched.append({
                    'location': location,
                    'count': count,
                    'city_name': extract_city_name(location)
                })
        
        # 显示结果
        print("=" * 80)
        print(f"✅ 已匹配的 location: {len(matched)} 个")
        print(f"❌ 未匹配的 location: {len(unmatched)} 个")
        print("=" * 80)
        
        if matched:
            print(f"\n✅ 已匹配的 location（显示前20个）：")
            print(f"{'Location':<30} {'出现次数':<10} {'映射省份':<20}")
            print("-" * 80)
            for item in sorted(matched, key=lambda x: x['count'], reverse=True)[:20]:
                print(f"{item['location']:<30} {item['count']:<10} {item['province']:<20}")
            if len(matched) > 20:
                print(f"... 还有 {len(matched) - 20} 个已匹配的 location")
        
        if unmatched:
            print(f"\n❌ 未匹配的 location（按出现次数排序）：")
            print(f"{'Location':<30} {'出现次数':<10} {'提取的城市名':<20}")
            print("-" * 80)
            for item in sorted(unmatched, key=lambda x: x['count'], reverse=True):
                print(f"{item['location']:<30} {item['count']:<10} {item['city_name']:<20}")
            
            # 统计未匹配的总记录数
            total_unmatched_count = sum(item['count'] for item in unmatched)
            total_count = sum(location_count_dict.values())
            matched_count = total_count - total_unmatched_count
            
            print(f"\n📈 统计信息：")
            print(f"   总记录数: {total_count}")
            print(f"   已匹配记录数: {matched_count} ({matched_count/total_count*100:.2f}%)")
            print(f"   未匹配记录数: {total_unmatched_count} ({total_unmatched_count/total_count*100:.2f}%)")
            
            # 提取未匹配的城市名，去重后显示
            unmatched_cities = set(item['city_name'] for item in unmatched if item['city_name'])
            print(f"\n💡 建议：以下 {len(unmatched_cities)} 个城市名可能需要添加到映射表：")
            for city in sorted(unmatched_cities):
                print(f"   - {city}")
        else:
            print("\n🎉 所有 location 都有对应的映射！")
        
    except Exception as e:
        print(f"❌ 检查过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("🔍 开始检查 job_listings 表中的 location 映射情况...\n")
    check_all_locations()
    print("\n✅ 检查完成！")

