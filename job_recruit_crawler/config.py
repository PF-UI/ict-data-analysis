"""
爬虫配置文件
"""
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(_CONFIG_DIR / ".env")
except ImportError:
    pass

# 输出目录（固定在本包目录下，不随当前工作目录变化）
OUTPUT_DIR = _CONFIG_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 爬虫配置
CRAWLER_CONFIG = {
    # 是否使用无头模式（建议False）
    "headless": False,
    
    # 是否等待手动登录
    "wait_login": True,
    
    # 每个搜索组合的最大页数
    "max_pages_per_search": 5,
    
    # 请求间隔（秒）
    "request_delay": 3,
    
    # 每N条数据保存一次
    "save_interval": 30,
    # 列表接口通常无完整「岗位职责/任职资格」，需点击左侧 job-info 加载右侧侧栏（默认 True）
    "fetch_detail_via_click": True,
    # 每页最多点击几条拉侧栏（与 joblist 每页条数一致即可，过大易断连）
    "detail_click_max_per_page": 15,
    # 两次点击之间的间隔（秒），略降低浏览器断连概率
    "detail_click_delay_sec": 1.5,
}

# ICT关键词列表（可在运行时修改）——广义 ICT：语言栈、前后端与移动端、嵌入式、AI/大模型与基础设施
ICT_KEYWORDS = [
    "软件开发",
    "物联网",
    "通信设备",
    "网络设备",
    "5G",
]

# 城市列表（可在运行时修改）
CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "南京",
    "武汉", "成都", "西安", "重庆", "天津", "苏州",
    "长沙", "郑州", "济南", "青岛", "大连", "厦门",
    "合肥", "福州", "石家庄", "沈阳", "哈尔滨", "长春"
]
