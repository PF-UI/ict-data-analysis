"""
清洗城市映射表的 full_name 字段
"""
import re
from app.database import SessionLocal
from app.models.city_mapping import CityMapping


def clean_full_name(full_name: str) -> str:
    """
    清洗省份名称
    
    规则：
    1. 去掉所有引号（单引号、双引号）
    2. 直辖市：北京、上海、天津、重庆（去掉"市"字）
    3. 省份：保持"省"字，如河北省、湖北省
    4. 自治区：保持"自治区"，如新疆维吾尔自治区、内蒙古自治区
    5. 特别行政区：保持"特别行政区"，如香港特别行政区、澳门特别行政区
    """
    if not full_name:
        return full_name
    
    # 去掉所有引号
    cleaned = full_name.strip().strip('"').strip("'").strip('""').strip("''")
    
    # 定义直辖市映射（需要去掉"市"字）
    municipalities = {
        '北京市': '北京',
        '上海市': '上海',
        '天津市': '天津',
        '重庆市': '重庆'
    }
    
    # 如果是直辖市，去掉"市"字
    if cleaned in municipalities:
        return municipalities[cleaned]
    
    # 如果以"市"结尾但不是直辖市，可能是错误数据，尝试去掉"市"字
    # 但这种情况应该很少，先保留原样
    
    # 确保省份名称格式正确
    # 省份应该以"省"结尾，如：河北省、湖北省
    # 自治区应该以"自治区"结尾，如：新疆维吾尔自治区
    # 特别行政区应该以"特别行政区"结尾
    
    # 如果已经是正确的格式，直接返回
    if cleaned.endswith('省') or cleaned.endswith('自治区') or cleaned.endswith('特别行政区'):
        return cleaned
    
    # 如果是直辖市但格式不对，修正
    if cleaned in ['北京', '上海', '天津', '重庆']:
        return cleaned
    
    # 如果只是省份简称，尝试补全（但这种情况应该很少，因为数据应该已经是全称）
    province_map = {
        '河北': '河北省',
        '山西': '山西省',
        '辽宁': '辽宁省',
        '吉林': '吉林省',
        '黑龙江': '黑龙江省',
        '江苏': '江苏省',
        '浙江': '浙江省',
        '安徽': '安徽省',
        '福建': '福建省',
        '江西': '江西省',
        '山东': '山东省',
        '河南': '河南省',
        '湖北': '湖北省',
        '湖南': '湖南省',
        '广东': '广东省',
        '海南': '海南省',
        '四川': '四川省',
        '贵州': '贵州省',
        '云南': '云南省',
        '陕西': '陕西省',
        '甘肃': '甘肃省',
        '青海': '青海省',
        '台湾': '台湾省',
        '内蒙古': '内蒙古自治区',
        '广西': '广西壮族自治区',
        '西藏': '西藏自治区',
        '宁夏': '宁夏回族自治区',
        '新疆': '新疆维吾尔自治区',
        '香港': '香港特别行政区',
        '澳门': '澳门特别行政区'
    }
    
    if cleaned in province_map:
        return province_map[cleaned]
    
    # 如果都不匹配，返回清理后的原始值
    return cleaned


def clean_city_mapping_table(dry_run: bool = True):
    """
    清洗城市映射表
    
    Args:
        dry_run: 如果为True，只显示将要修改的数据，不实际更新数据库
    """
    db = SessionLocal()
    try:
        # 获取所有城市映射记录
        mappings = db.query(CityMapping).all()
        
        print(f"📊 找到 {len(mappings)} 条城市映射记录\n")
        
        updates = []
        unchanged = []
        
        for mapping in mappings:
            original = mapping.full_name
            cleaned = clean_full_name(original)
            
            if original != cleaned:
                updates.append({
                    'short_name': mapping.short_name,
                    'original': original,
                    'cleaned': cleaned
                })
            else:
                unchanged.append({
                    'short_name': mapping.short_name,
                    'full_name': original
                })
        
        # 显示需要更新的记录
        if updates:
            print(f"🔄 需要更新 {len(updates)} 条记录：\n")
            for update in updates:
                print(f"  {update['short_name']:15} | {update['original']:30} → {update['cleaned']}")
            
            if not dry_run:
                print(f"\n💾 开始更新数据库...")
                for update in updates:
                    mapping = db.query(CityMapping).filter(
                        CityMapping.short_name == update['short_name']
                    ).first()
                    if mapping:
                        mapping.full_name = update['cleaned']
                        db.commit()
                print(f"✅ 成功更新 {len(updates)} 条记录")
            else:
                print(f"\n⚠️  这是预览模式（dry_run=True），未实际更新数据库")
                print(f"   如需实际更新，请运行: clean_city_mapping_table(dry_run=False)")
        else:
            print("✅ 所有记录格式正确，无需更新")
        
        # 显示未更改的记录（可选）
        if unchanged and len(unchanged) <= 20:
            print(f"\n✅ 以下 {len(unchanged)} 条记录格式正确，无需修改：")
            for item in unchanged[:10]:  # 只显示前10条
                print(f"  {item['short_name']:15} | {item['full_name']}")
            if len(unchanged) > 10:
                print(f"  ... 还有 {len(unchanged) - 10} 条记录")
        
    except Exception as e:
        print(f"❌ 清洗过程中发生错误: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    # 检查命令行参数
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] == "--execute":
        dry_run = False
        print("⚠️  警告：将实际更新数据库！\n")
    else:
        print("ℹ️  预览模式：只显示将要修改的数据，不会实际更新数据库")
        print("   如需实际更新，请运行: python clean_city_mapping.py --execute\n")
    
    # 执行清洗
    clean_city_mapping_table(dry_run=dry_run)
    
    if dry_run:
        print("\n" + "="*60)
        print("提示：运行 'python clean_city_mapping.py --execute' 来实际更新数据库")

