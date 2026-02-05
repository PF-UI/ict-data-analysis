"""
招聘信息相关路由
"""
import re
from collections import Counter
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from app.schemas.job_listing import JobListing, JobListingListResponse
from app.database import get_db
from app.models.job_listing import JobListing as JobListingModel
from app.models.city_mapping import CityMapping as CityMappingModel
from math import ceil

router = APIRouter()


@router.get("/", response_model=JobListingListResponse)
async def get_job_listings(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(20, ge=1, le=100, description="每页记录数"),
    job_title: Optional[str] = Query(None, description="职位名称（模糊搜索）"),
    company_name: Optional[str] = Query(None, description="公司名称（模糊搜索）"),
    location: Optional[str] = Query(None, description="工作地点（模糊搜索）"),
    search_keyword: Optional[str] = Query(None, description="搜索关键词"),
    data_year: Optional[int] = Query(None, description="数据年份"),
    db: Session = Depends(get_db)
):
    """
    获取招聘信息列表（分页）
    
    支持以下查询参数：
    - skip: 跳过记录数（默认: 0）
    - limit: 每页记录数（默认: 20，最大: 100）
    - job_title: 职位名称（模糊搜索）
    - company_name: 公司名称（模糊搜索）
    - location: 工作地点（模糊搜索）
    - search_keyword: 搜索关键词
    - data_year: 数据年份
    """
    # 构建查询
    query = db.query(JobListingModel)
    
    # 应用筛选条件
    if job_title:
        query = query.filter(JobListingModel.job_title.like(f"%{job_title}%"))
    
    if company_name:
        query = query.filter(JobListingModel.company_name.like(f"%{company_name}%"))
    
    if location:
        query = query.filter(JobListingModel.location.like(f"%{location}%"))
    
    if search_keyword:
        query = query.filter(
            or_(
                JobListingModel.job_title.like(f"%{search_keyword}%"),
                JobListingModel.company_name.like(f"%{search_keyword}%"),
                JobListingModel.requirements.like(f"%{search_keyword}%"),
                JobListingModel.search_keyword.like(f"%{search_keyword}%")
            )
        )
    
    if data_year:
        query = query.filter(JobListingModel.data_year == data_year)
    
    # 获取总记录数
    total = query.count()
    
    # 应用分页
    items = query.order_by(JobListingModel.created_at.desc()).offset(skip).limit(limit).all()
    
    # 计算分页信息
    page = (skip // limit) + 1 if limit > 0 else 1
    pages = ceil(total / limit) if limit > 0 else 1
    
    return JobListingListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        page=page,
        pages=pages
    )


@router.get("/salary-statistics")
async def get_salary_statistics(
    start_year: int = Query(2022, description="起始年份"),
    end_year: int = Query(2025, description="结束年份"),
    db: Session = Depends(get_db)
):
    """
    获取指定年份范围内的薪资分布统计
    
    基于 salary_avg 字段进行统计，按年份和薪资区间分组
    """
    def categorize_salary(salary_avg: int) -> str:
        """将平均薪资分类到薪资区间"""
        if salary_avg < 3000:
            return "3千以下"
        elif salary_avg < 5000:
            return "3-5千"
        elif salary_avg < 8000:
            return "5-8千"
        elif salary_avg < 10000:
            return "8千-1万"
        elif salary_avg < 15000:
            return "1-1.5万"
        elif salary_avg < 20000:
            return "1.5-2万"
        elif salary_avg < 30000:
            return "2-3万"
        elif salary_avg < 50000:
            return "3-5万"
        else:
            return "5万以上"
    
    # 查询指定年份范围内有平均薪资的数据
    query = db.query(
        JobListingModel.data_year,
        JobListingModel.salary_avg
    ).filter(
        JobListingModel.data_year >= start_year,
        JobListingModel.data_year <= end_year,
        JobListingModel.salary_avg.isnot(None),
        JobListingModel.salary_avg > 0
    )
    
    results = query.all()
    
    # 按年份和薪资区间统计
    statistics = {}
    year_list = set()
    
    for year, salary_avg in results:
        if year:
            year_list.add(year)
            category = categorize_salary(salary_avg)
            
            if year not in statistics:
                statistics[year] = {}
            statistics[year][category] = statistics[year].get(category, 0) + 1
    
    # 构建返回数据结构
    categories = ["3千以下", "3-5千", "5-8千", "8千-1万", "1-1.5万", 
                  "1.5-2万", "2-3万", "3-5万", "5万以上"]
    
    years = sorted(year_list)
    
    # 确保每个年份都有所有分类（缺失的为0）
    result_data = {}
    for year in years:
        result_data[year] = {
            category: statistics[year].get(category, 0) 
            for category in categories
        }
    
    return {
        "years": years,
        "categories": categories,
        "data": result_data
    }


@router.get("/location-statistics")
async def get_location_statistics(
    start_year: int = Query(2022, description="起始年份"),
    end_year: int = Query(2025, description="结束年份"),
    db: Session = Depends(get_db)
):
    """
    获取指定年份范围内的招聘数据地理分布统计
    
    返回每个省份的招聘职位数量，按年份分组
    """
    # 预先加载城市映射表（只查询一次，避免重复查询）
    city_mappings = db.query(CityMappingModel).all()
    city_map = {mapping.short_name: mapping.full_name for mapping in city_mappings}
    
    # 构建反向映射，用于快速查找（城市名 -> 省份）
    # 这样可以避免在循环中进行嵌套查找
    reverse_map = {}
    for short_name, full_name in city_map.items():
        # 为每个简称创建多个可能的匹配键
        reverse_map[short_name] = full_name
        # 如果简称包含常见后缀，也添加无后缀版本
        if short_name.endswith('市'):
            reverse_map[short_name[:-1]] = full_name
    
    # 查询指定年份范围内的招聘数据
    query = db.query(
        JobListingModel.data_year,
        JobListingModel.location
    ).filter(
        JobListingModel.data_year >= start_year,
        JobListingModel.data_year <= end_year,
        JobListingModel.location.isnot(None),
        JobListingModel.location != ''
    )
    
    results = query.all()
    
    # 将地点转换为省份（优化版：减少嵌套循环）
    def location_to_province(location: str) -> str:
        """将地点转换为省份名称，仅使用映射表（优化版）"""
        if not location:
            return "未知"
        
        location = location.strip()
        
        # 处理格式如 "武汉-江夏区"、"北京"、"上海" 等
        # 提取城市名（第一个"-"前的部分，去掉"市"字）
        city_name = location.split('-')[0].split('市')[0].strip()
        
        # 首先尝试完整匹配（最快）
        if city_name in city_map:
            return city_map[city_name]
        
        # 尝试反向映射查找
        if city_name in reverse_map:
            return reverse_map[city_name]
        
        # 尝试部分匹配（优化：只遍历一次，找到即返回）
        for short_name, full_name in city_map.items():
            # 检查映射表的简称是否在地点中
            if short_name in location or location.startswith(short_name):
                return full_name
            # 检查地点是否在映射表的简称中（如"武汉"匹配"武汉"）
            if city_name in short_name or short_name in city_name:
                return full_name
        
        # 如果映射表中没有找到，返回"未知"
        return "未知"
    
    # 按年份和省份统计（使用字典优化）
    statistics = {}
    year_list = set()
    province_set = set()
    
    for year, location in results:
        if year and location:
            year_list.add(year)
            province = location_to_province(location)
            province_set.add(province)
            
            if year not in statistics:
                statistics[year] = {}
            statistics[year][province] = statistics[year].get(province, 0) + 1
    
    years = sorted(year_list)
    provinces = sorted(list(province_set))
    
    # 确保每个年份都有所有省份（缺失的为0）
    result_data = {}
    for year in years:
        result_data[year] = {
            province: statistics[year].get(province, 0) 
            for province in provinces
        }
    
    return {
        "years": years,
        "provinces": provinces,
        "data": result_data
    }


@router.get("/wordcloud-statistics")
async def get_wordcloud_statistics(
    start_year: int = Query(2022, description="起始年份"),
    end_year: int = Query(2025, description="结束年份"),
    top_n: int = Query(100, ge=10, le=500, description="返回前N个高频词"),
    min_length: int = Query(2, ge=1, le=10, description="词汇最小长度"),
    db: Session = Depends(get_db)
):
    """
    获取指定年份范围内的招聘要求词云统计数据
    
    从 requirements 字段中提取中文词汇，统计词频，返回词云图所需的数据格式
    """
    # 查询指定年份范围内的招聘数据
    query = db.query(
        JobListingModel.data_year,
        JobListingModel.requirements
    ).filter(
        JobListingModel.data_year >= start_year,
        JobListingModel.data_year <= end_year,
        JobListingModel.requirements.isnot(None),
        JobListingModel.requirements != ''
    )
    
    results = query.all()
    
    # 停用词列表（常见无意义词汇）
    stop_words = {
        '的', '了', '和', '是', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这',
        '年', '月', '日', '时', '分', '秒', '个', '条', '项', '种', '类', '等', '及', '或', '与', '为', '以', '在', '有', '能', '可', '会', '需', '要', '应',
        '具备', '具有', '拥有', '掌握', '熟悉', '了解', '负责', '完成', '参与', '协助', '支持', '工作', '经验', '能力', '技能', '知识', '学历', '专业',
        '优先', '加分', '要求', '条件', '以上', '以下', '左右', '至少', '以上', '相关', '相关专业', '相关经验'
    }
    
    # 按年份统计词频
    year_word_counts = {}
    all_words = []
    
    for year, requirements in results:
        if not year or not requirements:
            continue
        
        # 提取中文词汇（2-10个字符）
        # 匹配中文字符、数字、英文字母的组合
        words = re.findall(r'[\u4e00-\u9fa5]{' + str(min_length) + r',10}', requirements)
        
        # 过滤停用词和过短/过长的词
        filtered_words = [
            word for word in words 
            if word not in stop_words 
            and len(word) >= min_length 
            and len(word) <= 10
        ]
        
        if year not in year_word_counts:
            year_word_counts[year] = []
        
        year_word_counts[year].extend(filtered_words)
        all_words.extend(filtered_words)
    
    # 统计所有年份的总词频
    all_word_counter = Counter(all_words)
    top_words = all_word_counter.most_common(top_n)
    
    # 按年份统计词频
    year_statistics = {}
    years = sorted(year_word_counts.keys())
    
    for year in years:
        year_counter = Counter(year_word_counts[year])
        # 只保留在总词频top_n中的词
        year_top_words = {
            word: count 
            for word, count in year_counter.items() 
            if word in dict(top_words)
        }
        year_statistics[year] = year_top_words
    
    # 构建词云数据格式：[{name: "词汇", value: 词频}, ...]
    wordcloud_data = [
        {"name": word, "value": count}
        for word, count in top_words
    ]
    
    return {
        "years": years,
        "wordcloud": wordcloud_data,
        "year_statistics": year_statistics,
        "total_words": len(all_words),
        "unique_words": len(all_word_counter)
    }


@router.get("/{job_id}", response_model=JobListing)
async def get_job_listing(
    job_id: int,
    db: Session = Depends(get_db)
):
    """
    根据ID获取单个招聘信息
    """
    job_listing = db.query(JobListingModel).filter(JobListingModel.id == job_id).first()
    if job_listing is None:
        raise HTTPException(status_code=404, detail="招聘信息未找到")
    return job_listing

