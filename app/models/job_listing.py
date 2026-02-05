"""
招聘信息数据库模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base


class JobListing(Base):
    """招聘信息表模型"""
    __tablename__ = "job_listings"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="主键ID")
    job_title = Column(String(250), nullable=False, index=True, comment="职位名称")
    company_name = Column(String(250), nullable=False, index=True, comment="公司名称")
    salary_range = Column(String(100), nullable=True, comment="薪资范围")
    salary_avg = Column(Integer, nullable=True, index=True, comment="平均月薪（元）")
    location = Column(String(100), nullable=True, index=True, comment="工作地点")
    openings = Column(Integer, nullable=True, default=1, comment="招聘人数")
    requirements = Column(Text, nullable=True, comment="职位要求")
    search_keyword = Column(String(100), nullable=True, index=True, comment="搜索关键词")
    data_year = Column(Integer, nullable=True, index=True, comment="数据年份")
    # MySQL 不支持 timezone=True，使用普通 DateTime
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    
    def __repr__(self):
        return f"<JobListing(id={self.id}, job_title={self.job_title}, company_name={self.company_name})>"

