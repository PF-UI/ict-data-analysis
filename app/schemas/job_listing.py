"""
招聘信息数据模式
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class JobListingBase(BaseModel):
    """招聘信息基础模式"""
    job_title: str = Field(..., max_length=250, description="职位名称")
    company_name: str = Field(..., max_length=250, description="公司名称")
    salary_range: Optional[str] = Field(None, max_length=100, description="薪资范围")
    salary_avg: Optional[int] = Field(None, description="平均月薪（元）")
    location: Optional[str] = Field(None, max_length=100, description="工作地点")
    openings: Optional[int] = Field(None, ge=0, description="招聘人数")
    requirements: Optional[str] = Field(None, description="职位要求")
    search_keyword: Optional[str] = Field(None, max_length=100, description="搜索关键词")
    data_year: Optional[int] = Field(None, description="数据年份")


class JobListingCreate(JobListingBase):
    """创建招聘信息模式"""
    pass


class JobListingUpdate(BaseModel):
    """更新招聘信息模式"""
    job_title: Optional[str] = Field(None, max_length=250, description="职位名称")
    company_name: Optional[str] = Field(None, max_length=250, description="公司名称")
    salary_range: Optional[str] = Field(None, max_length=100, description="薪资范围")
    salary_avg: Optional[int] = Field(None, description="平均月薪（元）")
    location: Optional[str] = Field(None, max_length=100, description="工作地点")
    openings: Optional[int] = Field(None, ge=0, description="招聘人数")
    requirements: Optional[str] = Field(None, description="职位要求")
    search_keyword: Optional[str] = Field(None, max_length=100, description="搜索关键词")
    data_year: Optional[int] = Field(None, description="数据年份")


class JobListing(JobListingBase):
    """招聘信息响应模式"""
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class JobListingListResponse(BaseModel):
    """招聘信息列表响应模式（包含分页信息）"""
    items: List[JobListing] = Field(..., description="招聘信息列表")
    total: int = Field(..., description="总记录数")
    skip: int = Field(..., description="跳过记录数")
    limit: int = Field(..., description="每页记录数")
    page: int = Field(..., description="当前页码")
    pages: int = Field(..., description="总页数")

