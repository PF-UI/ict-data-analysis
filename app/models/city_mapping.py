"""
城市映射数据库模型
"""
from sqlalchemy import Column, String
from app.database import Base


class CityMapping(Base):
    """城市映射表模型"""
    __tablename__ = "city_mapping"
    
    short_name = Column(String(255), primary_key=True, index=True, comment="城市简称")
    full_name = Column(String(255), nullable=False, comment="省份全称")
    
    def __repr__(self):
        return f"<CityMapping(short_name={self.short_name}, full_name={self.full_name})>"

