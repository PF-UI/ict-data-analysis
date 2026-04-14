# -*- coding: utf-8 -*-
"""
Boss直聘爬虫 - 使用DrissionPage监听API接口
自动获取ICT相关招聘数据，支持全国搜索
"""
import json
import sys
import os
from pathlib import Path
from time import sleep

# 无论从仓库根目录还是本目录运行，都能导入同目录下的 config
_CRAWLER_DIR = Path(__file__).resolve().parent
if str(_CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(_CRAWLER_DIR))

# Windows控制台编码设置
if sys.platform == 'win32':
    try:
        # 设置控制台代码页为UTF-8
        os.system('chcp 65001 >nul 2>&1')
    except:
        pass

# 导入DrissionPage
try:
    from DrissionPage import ChromiumPage, ChromiumOptions
except ImportError as e:
    print(f"❌ 无法导入DrissionPage: {e}")
    print(f"Python路径: {sys.executable}")
    print(f"模块搜索路径:")
    for p in sys.path:
        print(f"  - {p}")
    raise

from typing import List, Set, Optional, Dict
from datetime import datetime
import re
import unicodedata
import pandas as pd

# 导入配置（如果config.py不存在，使用默认值）
try:
    from config import ICT_KEYWORDS, OUTPUT_DIR, CRAWLER_CONFIG
except ImportError:
    # 如果config.py不存在，使用默认配置
    OUTPUT_DIR = Path("output")
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    CRAWLER_CONFIG = {
        "headless": False,
        "wait_login": True,
        "max_pages_per_search": 5,
        "request_delay": 3,
        "save_interval": 30,  # 每30条保存一次
        "page_size": 30,  # 每页30条
        "fetch_detail_via_click": True,
        "detail_click_max_per_page": 15,
        "detail_click_delay_sec": 1.5,
    }
    
    ICT_KEYWORDS = [
        "ICT", "信息通信技术", "通信技术",
        "5G", "物联网", "IoT", "云计算", "大数据",
        "人工智能", "AI", "网络安全", "网络工程",
        "通信工程", "系统集成", "ICT项目经理",
        "通信工程师", "网络工程师", "ICT咨询",
        "信息通信", "通信设备", "网络设备",
        "移动通信", "无线通信", "光通信"
    ]


class BossZhipinCrawler:
    """Boss直聘爬虫类 - 使用DrissionPage监听API"""
    
    def __init__(self, wait_login: bool = True, use_click_mode: bool = True):
        """
        初始化爬虫
        :param wait_login: 是否等待手动登录
        :param use_click_mode: 是否使用点击模式（True=点击列表项获取详情，False=监听API接口）
        """
        self.dp = None
        self.wait_login = wait_login
        self.use_click_mode = use_click_mode  # 是否使用点击模式
        
        # ICT相关关键词列表
        self.ict_keywords = ICT_KEYWORDS.copy()
        
        # 全国城市代码（100010000表示全国）
        self.city_code = "100010000"
        self.city_name = "全国"
        
        # 用于去重的集合（使用jobId作为唯一标识）
        self.seen_job_ids: Set[str] = set()
        self.all_jobs: List[Dict] = []
        
        # 输出目录
        self.output_dir = OUTPUT_DIR
        self.output_dir.mkdir(exist_ok=True)
        
        # 中断标志
        self.interrupted = False
    
    @staticmethod
    def geek_jobs_search_url(keyword: str, city_code: str) -> str:
        """Boss Web 端职位列表（与站点一致使用 /web/geek/jobs），query 必须 URL 编码。"""
        from urllib.parse import quote
        return (
            f"https://www.zhipin.com/web/geek/jobs"
            f"?query={quote(str(keyword), safe='')}&city={quote(str(city_code), safe='')}"
        )
    
    def _is_geek_job_search_page(self, url: Optional[str] = None) -> bool:
        """
        是否为求职者搜索列表页。
        注意：官方 URL 多为 /web/geek/jobs?...，不能用 'job?' in url 判断（jobs? 不含 job? 子串）。
        """
        u = (url or "").strip()
        if not u:
            return False
        ul = u.lower()
        if "zhipin.com" not in ul:
            return False
        if "/web/geek/job" not in ul:
            return False
        if "job_detail" in ul:
            return False
        return True
    
    @staticmethod
    def _list_api_job_description(job: Dict) -> str:
        """职位列表接口里可能出现的描述字段（不同版本字段名不同）。"""
        for k in ("jobDesc", "postDescription", "jobDescription", "encryptJobDesc"):
            v = job.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ""
    
    @staticmethod
    def _split_duty_and_requirement(text: str) -> tuple:
        """侧栏 p.desc 常为「岗位职责…任职资格…」一整段，拆成两列字段。"""
        if not text or not str(text).strip():
            return "", ""
        t = unicodedata.normalize("NFKC", str(text).strip())
        # 以「任职资格/任职要求」为界：前为职责，后为要求
        m = re.search(r"(任职资格|任职要求|岗位要求)", t)
        if m:
            duty = t[: m.start()].strip()
            req = t[m.end() :].strip()
            duty = re.sub(
                r"^(工作职责|岗位职责|工作内容|职位描述)[：:\s\d、．.]*",
                "",
                duty,
                flags=re.MULTILINE,
            ).strip()
            return duty, req
        return t, ""
    
    @staticmethod
    def _clean_side_panel_text(text: str) -> str:
        """去掉侧栏 .job-detail-body 里举报/分享/App/招聘者尾段等噪声，保留职责与要求正文。"""
        if not text or not str(text).strip():
            return ""
        t = unicodedata.normalize("NFKC", str(text))
        noise_kw = (
            "举报",
            "微信扫码",
            "扫码分享",
            "去app",
            "前往app",
            "与boss",
            "今日活跃",
            "随时沟通",
            "招聘经理",
            "前往下载",
        )
        lines_out = []
        for line in t.splitlines():
            s = line.strip()
            if not s:
                continue
            low = s.lower()
            if any(k in low for k in noise_kw):
                continue
            if re.search(r"先生|女士", s) and re.search(r"活跃|招聘经理|沟通", s):
                continue
            if re.match(r"^[\s·•]+$", s):
                continue
            lines_out.append(s)
        out = "\n".join(lines_out).strip()
        out = re.sub(r"^职位描述\s*$", "", out, flags=re.MULTILINE).strip()
        return out.strip()
    
    def apply_desc_flex_for_full_text(self) -> None:
        """
        Boss 直聘 /web/geek/jobs 职位详情侧栏中 p.desc 默认为 display:block，
        在部分布局下会导致 innerText/可见文本不完整。抓取前改为 flex 布局以展开全文。
        """
        if not self.dp:
            return
        fix_js = """
        (function() {
            var list = document.querySelectorAll('p.desc');
            for (var i = 0; i < list.length; i++) {
                var el = list[i];
                el.style.setProperty('display', 'flex', 'important');
                el.style.setProperty('flex-direction', 'column', 'important');
                el.style.setProperty('overflow', 'visible', 'important');
                el.style.setProperty('max-height', 'none', 'important');
                el.style.setProperty('height', 'auto', 'important');
                el.style.setProperty('white-space', 'pre-wrap', 'important');
            }
            return list.length;
        })();
        """
        try:
            self.dp.run_js(fix_js)
        except Exception:
            pass
    
    def _find_job_card_root(self, start):
        """从子节点向上查找 li.job-card-box，用于读取公司/薪资等。"""
        el = start
        for _ in range(10):
            if not el:
                return None
            try:
                if el.tag and str(el.tag).lower() == 'li' and 'job-card-box' in (el.attr('class') or ''):
                    return el
            except Exception:
                pass
            try:
                el = el.parent()
            except Exception:
                break
        return None
    
    def init_browser(self):
        """初始化浏览器"""
        print("🚀 正在初始化浏览器...")
        
        try:
            # 配置浏览器选项
            co = ChromiumOptions()
            co.headless(False)  # 不使用无头模式，方便观察和登录
            
            # 创建浏览器页面对象
            self.dp = ChromiumPage(co)
            
            # 等待浏览器完全启动
            sleep(2)
            
            # 检查初始URL（可能自动跳转）
            try:
                initial_url = self.dp.url
                print(f"  💡 浏览器初始URL: {initial_url}")
                
                # 如果跳转到非搜索页，先访问首页
                if 'jobs?ka=header' in initial_url or 'wuhan' in initial_url or 'gongsi' in initial_url:
                    print(f"  ⚠️  检测到初始页面跳转，访问Boss直聘首页...")
                    self.dp.get('https://www.zhipin.com')
                    sleep(3)
            except:
                pass
            
            print("✅ 浏览器初始化成功")
        except Exception as e:
            print(f"❌ 浏览器初始化失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def check_login_status(self):
        """检查登录状态"""
        try:
            # 检查页面是否有登录相关元素
            # 如果URL包含login或passport，说明需要登录
            if "login" in self.dp.url.lower() or "passport" in self.dp.url.lower():
                return False
            
            # 检查页面是否有职位列表（登录后应该能看到职位）
            sleep(2)  # 等待页面加载
            try:
                # 尝试查找职位列表元素
                job_list = self.dp.eles('tag:li', timeout=2)
                if job_list and len(job_list) > 0:
                    return True
            except:
                pass
            
            # 检查是否有"登录/注册"按钮（未登录状态）
            try:
                login_btn = self.dp.ele('text:登录', timeout=1)
                if login_btn:
                    return False
            except:
                pass
            
            return True
        except:
            return False
    
    def close_browser(self):
        """关闭浏览器"""
        try:
            if self.dp:
                # 停止监听
                try:
                    self.dp.listen.stop()
                except:
                    pass
                # 关闭浏览器
                try:
                    self.dp.quit()
                except:
                    pass
                self.dp = None
                print("  ✅ 浏览器已关闭")
        except Exception as e:
            print(f"  ⚠️  关闭浏览器时出错: {e}")
    
    def wait_for_login(self):
        """等待用户登录"""
        if not self.wait_login:
            return
        
        # 先检查是否已登录
        if self.check_login_status():
            print("✅ 已登录，继续执行...")
            return
        
        print("\n" + "="*50)
        print("⚠️  检测到需要登录")
        print("📝 请在浏览器中完成登录操作")
        print("💡 登录后，页面应该显示职位列表")
        print("✅ 登录完成后，请在控制台按回车继续...")
        print("="*50)
        input()
        
        # 再次检查登录状态
        if not self.check_login_status():
            print("⚠️  登录状态未确认，请确保已成功登录")
            print("💡 如果已登录，请按回车继续...")
            input()
        
        print("✅ 继续执行爬取任务...\n")
    
    def search_jobs_by_keyword(self, keyword: str, max_pages: int = 10) -> List[Dict]:
        """
        搜索指定关键词的职位
        :param keyword: 搜索关键词
        :param max_pages: 最大爬取页数
        :return: 职位列表
        """
        jobs = []
        # 使用局部变量记录本次搜索已见过的职位ID（仅用于本次搜索内去重）
        local_seen_ids = set()
        
        try:
            # 访问Boss直聘搜索页（全国搜索）；与站点一致使用 /web/geek/jobs
            url = self.geek_jobs_search_url(keyword, self.city_code)
            print(f"  📍 访问: {url}")
            
            # 先检查当前页面，如果已经跳转，先访问首页
            try:
                current_url = self.dp.url
                if 'jobs?ka=header' in current_url or ('wuhan' in current_url and '/?ka=' in current_url):
                    print(f"  ⚠️  当前页面已跳转，先访问首页...")
                    self.dp.get('https://www.zhipin.com')
                    sleep(3)
            except:
                pass
            
            # 必须在发起导航前监听，否则首屏 joblist.json 已发出且无法被捕获
            try:
                self.dp.listen.stop()
            except Exception:
                pass
            print(f"  🎧 监听 joblist 接口...")
            self.dp.listen.start('joblist')
            
            # 访问搜索页
            self.dp.get(url)
            sleep(5)  # 等待页面加载（增加等待时间）
            
            # 检查页面是否跳转（更精确的检测）
            try:
                current_url = self.dp.url
                print(f"  💡 访问后页面URL: {current_url}")
                
                # 检测跳转：jobs?ka=header-jobs 或 wuhan/?ka=header 或 gongsi/company 或 school/?ka=
                is_redirected = False
                if 'jobs?ka=header' in current_url:
                    is_redirected = True
                    print(f"  ⚠️  检测到跳转到 jobs?ka=header-jobs")
                elif 'wuhan' in current_url and '/?ka=' in current_url:
                    is_redirected = True
                    print(f"  ⚠️  检测到跳转到 wuhan/?ka= (可能是 header-home 或其他)")
                elif 'gongsi' in current_url or 'company' in current_url:
                    is_redirected = True
                    print(f"  ⚠️  检测到跳转到公司页面")
                elif 'school/?ka=' in current_url:
                    is_redirected = True
                    print(f"  ⚠️  检测到跳转到 school/?ka=tab_school_recruit_click")
                
                if is_redirected:
                    print(f"  ⚠️  页面跳转，尝试重新访问搜索页...")
                    # 先访问首页，再访问搜索页
                    self.dp.get('https://www.zhipin.com')
                    sleep(3)
                    self.dp.get(url)
                    sleep(5)
                    
                    # 再次检查
                    current_url = self.dp.url
                    if 'jobs?ka=header' in current_url or ('wuhan' in current_url and '/?ka=' in current_url) or 'gongsi' in current_url or 'company' in current_url or 'school/?ka=' in current_url:
                        print(f"  ❌ 页面仍然跳转，可能被重定向或需要登录，跳过此关键词")
                        return jobs
                    else:
                        print(f"  ✅ 重新访问成功，当前URL: {current_url}")
            except Exception as e:
                print(f"  ⚠️  检查URL时出错: {e}")
                pass
            
            # 尝试修改API请求的pageSize参数为30
            # 通过拦截和修改fetch/XMLHttpRequest请求
            try:
                set_page_size_js = """
                (function() {
                    // 拦截fetch请求
                    const originalFetch = window.fetch;
                    window.fetch = function(...args) {
                        if (args[0] && typeof args[0] === 'string' && args[0].includes('joblist')) {
                            // 如果是joblist接口，修改URL参数
                            const url = new URL(args[0], window.location.origin);
                            url.searchParams.set('pageSize', '30');
                            args[0] = url.toString();
                        }
                        return originalFetch.apply(this, args);
                    };
                    
                    // 拦截XMLHttpRequest
                    const originalOpen = XMLHttpRequest.prototype.open;
                    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                        if (url && url.includes('joblist')) {
                            const urlObj = new URL(url, window.location.origin);
                            urlObj.searchParams.set('pageSize', '30');
                            url = urlObj.toString();
                        }
                        return originalOpen.call(this, method, url, ...rest);
                    };
                    
                    console.log('✅ 已设置pageSize拦截器为30');
                })();
                """
                self.dp.run_js(set_page_size_js)
            except Exception as e:
                print(f"  ⚠️  设置pageSize失败: {e}，使用默认值")
            
            # 检查是否需要登录（改进的检测逻辑）
            # 先检查当前URL，如果跳转到登录页或首页，可能需要登录
            try:
                current_url = self.dp.url
                if 'login' in current_url or 'passport' in current_url or 'jobs?ka=header' in current_url:
                    print(f"  ⚠️  检测到可能需要登录（URL: {current_url}）")
                    if not self.check_login_status():
                        print(f"  ⚠️  需要登录")
                        self.wait_for_login()
                        # 重新访问搜索页
                        self.dp.get(url)
                        sleep(5)
                        # 再次确认登录状态和URL
                        current_url = self.dp.url
                        if 'jobs?ka=header' in current_url or ('wuhan' in current_url and '/?ka=header' in current_url):
                            print(f"  ❌ 登录后仍然跳转，可能无法访问，跳过此关键词")
                            return jobs
                        if not self.check_login_status():
                            print(f"  ❌ 登录状态未确认，跳过此关键词")
                            return jobs
            except Exception as e:
                print(f"  ⚠️  检查登录状态时出错: {e}")
                # 继续尝试，不中断
            
            print(f"  🔍 开始分页采集 {max_pages} 页（监听已开启）...")

            # 循环爬取指定页数
            for page in range(max_pages):
                # 检查中断标志
                if self.interrupted:
                    print(f"\n⚠️  检测到中断信号，停止爬取...")
                    break
                
                print(f"\n  📄 正在采集第 {page + 1} 页数据...")
                
                try:
                    # 第一页：等待初始数据加载
                    if page == 0:
                        # 等待页面初始加载完成
                        sleep(3)
                        # 检查是否有初始API响应（可能页面加载时已经触发）
                        try:
                            steps = self.dp.listen.steps()
                            if steps:
                                print(f"  ✅ 检测到 {len(steps)} 个已捕获的API响应")
                                resp = steps[-1]  # 使用最后一个响应
                            else:
                                resp = self.dp.listen.wait(timeout=5)
                        except:
                            resp = self.dp.listen.wait(timeout=5)
                    else:
                        # 后续页：Boss直聘使用无限滚动，滚动到底部触发加载
                        print(f"  📜 滚动到底部触发加载第 {page + 1} 页数据...")
                        
                        # 记录当前已捕获的API响应数量，用于判断是否有新响应
                        try:
                            steps_before = self.dp.listen.steps()
                            steps_count_before = len(steps_before) if steps_before else 0
                        except:
                            steps_count_before = 0
                        
                        # 滚动到底部，触发无限滚动加载
                        # 多次滚动确保触发加载
                        for scroll_attempt in range(3):
                            self.dp.scroll.to_bottom()
                            sleep(1.5)  # 等待滚动完成和加载
                        
                        # 等待新的API响应（无限滚动会触发新的API请求）
                        print(f"  ⏳ 等待新的API响应...")
                        # 使用较短的超时时间，并在循环中检查中断标志
                        resp = None
                        for wait_attempt in range(15):  # 最多等待15秒，每秒检查一次
                            if self.interrupted:
                                print(f"  ⚠️  检测到中断信号，停止等待...")
                                break
                            try:
                                resp = self.dp.listen.wait(timeout=1)
                                if resp:
                                    break
                            except:
                                pass
                            sleep(0.5)  # 短暂等待
                        
                        # 如果wait()没有返回，检查是否有新的响应被捕获
                        if not resp:
                            try:
                                steps_after = self.dp.listen.steps()
                                steps_count_after = len(steps_after) if steps_after else 0
                                
                                if steps_count_after > steps_count_before:
                                    # 有新的响应被捕获，使用最新的响应
                                    resp = steps_after[-1]
                                    print(f"  ✅ 检测到新的API响应（响应数量: {steps_count_before} -> {steps_count_after}）")
                                elif steps_count_after > 0:
                                    # 虽然没有新响应，但可以使用最后一个响应（可能是同一页但数据更新了）
                                    resp = steps_after[-1]
                                    print(f"  💡 使用最后一个API响应（可能仍是同一页数据）")
                            except:
                                pass
                    
                    # 如果wait()没有返回，尝试从监听队列获取
                    if not resp:
                        try:
                            steps = self.dp.listen.steps()
                            if steps:
                                # 获取新的响应（比之前处理的更多）
                                if len(steps) > page:
                                    resp = steps[page]
                                else:
                                    resp = steps[-1] if steps else None
                        except:
                            pass
                    
                    if not resp:
                        print(f"  ⚠️  第 {page + 1} 页：未获取到API响应")
                        
                        # 尝试从已监听的响应中获取（可能已经捕获但未处理）
                        try:
                            steps = self.dp.listen.steps()
                            if steps:
                                print(f"  💡 从监听队列中获取到 {len(steps)} 个响应")
                                resp = steps[-1]  # 使用最后一个响应
                        except:
                            pass
                        
                        if not resp:
                            # 备用方案：如果是第一页，尝试从DOM提取
                            if page == 0:
                                print(f"  💡 尝试从页面DOM提取数据...")
                                dom_jobs = self.extract_jobs_from_dom()
                                if dom_jobs and len(dom_jobs) > 0:
                                    print(f"  ✅ 从DOM提取到 {len(dom_jobs)} 条职位")
                                    # 添加到jobs列表，并设置搜索关键词
                                    for dom_job in dom_jobs:
                                        dom_job['搜索关键词'] = keyword
                                        # 生成职位ID
                                        if not dom_job.get('职位ID') or dom_job.get('职位ID', '').startswith('dom_'):
                                            job_id = f"{dom_job.get('岗位名称', '')}_{dom_job.get('公司名称', '')}_{dom_job.get('工作地点', '')}"
                                            if job_id and job_id != '__':
                                                dom_job['职位ID'] = job_id
                                    jobs.extend(dom_jobs)
                                    print(f"  ✅ DOM提取完成，共 {len(jobs)} 条职位")
                                    # 继续尝试API方式获取后续页（不break）
                                    sleep(2)
                                    continue
                                else:
                                    print(f"  ⚠️  DOM提取未获取到数据")
                            
                            # 如果仍然没有响应，尝试继续下一页
                            if page < max_pages - 1:
                                print(f"  ⏳ 等待2秒后继续...")
                                sleep(2)
                            continue
                    
                    # 3. 解析JSON数据
                    try:
                        json_data = resp.response.body
                        
                        # 如果是字符串，需要解析
                        if isinstance(json_data, (str, bytes)):
                            if isinstance(json_data, bytes):
                                json_data = json_data.decode('utf-8')
                            json_data = json.loads(json_data)
                    except Exception as e:
                        print(f"  ⚠️  解析JSON失败: {e}")
                        # 尝试从响应文本解析
                        try:
                            json_data = json.loads(resp.response.text)
                        except:
                            print(f"  ❌ 无法解析响应数据")
                            continue
                    
                    # 检查数据结构
                    if not json_data or 'zpData' not in json_data:
                        print(f"  ⚠️  第 {page + 1} 页：API返回数据格式异常")
                        break
                    
                    # 检查API返回的页码信息和数据
                    zp_data = json_data.get('zpData', {})
                    api_page = zp_data.get('page', zp_data.get('currentPage', 0))
                    total_pages = zp_data.get('totalPage', zp_data.get('totalPages', 0))
                    total_count = zp_data.get('totalCount', 0)
                    
                    # 检查API请求的URL，看看page参数
                    try:
                        request_url = resp.request.url if hasattr(resp, 'request') and hasattr(resp.request, 'url') else ''
                        if request_url and ('page=' in request_url or 'pageNum=' in request_url):
                            print(f"  📊 API请求URL: {request_url[:120]}...")
                    except:
                        pass
                    
                    print(f"  📊 API返回信息: 当前页={api_page}, 总页数={total_pages}, 总条数={total_count}")
                    
                    job_list = zp_data.get('jobList', [])
                    
                    if not job_list:
                        print(f"  ℹ️  第 {page + 1} 页：暂无更多数据")
                        break
                    
                    # 检查是否有重复数据（如果所有职位ID都在之前见过，可能是同一页数据）
                    new_job_ids = set()
                    duplicate_count = 0
                    for job in job_list:
                        job_id = str(job.get('encryptJobId', job.get('jobId', '')))
                        if job_id:
                            if job_id in local_seen_ids:
                                duplicate_count += 1
                            else:
                                new_job_ids.add(job_id)
                    
                    if duplicate_count > 0:
                        print(f"  ⚠️  检测到 {duplicate_count}/{len(job_list)} 条重复数据（可能获取到同一页数据）")
                        # 如果重复率太高（超过80%），可能是同一页数据
                        if duplicate_count / len(job_list) > 0.8:
                            print(f"  ⚠️  重复率过高，可能没有真正翻页，跳过此页")
                            continue
                    else:
                        print(f"  ✅ 检测到 {len(new_job_ids)} 条新数据")
                    
                    # 4. 提取关键字段
                    page_jobs_count = 0
                    for idx, job in enumerate(job_list):
                        # 检查中断标志
                        if self.interrupted:
                            print(f"\n⚠️  检测到中断信号，停止处理职位...")
                            break
                        
                        try:
                            # 使用jobId作为唯一标识
                            job_id = str(job.get('encryptJobId', job.get('jobId', '')))
                            
                            # 如果job_id为空，生成一个临时ID
                            if not job_id or job_id == 'None' or job_id == '':
                                # 使用职位名称+公司名称+城市作为唯一标识
                                job_id = f"{job.get('jobName', '')}_{job.get('brandName', '')}_{job.get('cityName', '')}"
                                if not job_id or job_id == '__':
                                    job_id = f"job_{page}_{idx}_{len(jobs)}"
                            
                            # 去重检查（仅在本次搜索内去重，不添加到全局seen_job_ids）
                            if job_id in local_seen_ids:
                                continue
                            
                            local_seen_ids.add(job_id)
                            
                            # 处理工作地点：城市+区域+商圈
                            city_name = job.get('cityName', '')
                            area_district = job.get('areaDistrict', '')
                            business_district = job.get('businessDistrict', '')
                            
                            if area_district and business_district:
                                work_location = f"{city_name}-{area_district}-{business_district}"
                            elif area_district:
                                work_location = f"{city_name}-{area_district}"
                            else:
                                work_location = city_name or self.city_name
                            
                            # 提取核心字段
                            job_info = {
                                '职位ID': job_id,
                                '岗位名称': job.get('jobName', ''),
                                '工作地点': work_location,
                                '城市': city_name or self.city_name,
                                '区域': area_district,
                                '商圈': business_district,
                                '学历要求': job.get('jobDegree', ''),
                                '工作经验': job.get('jobExperience', ''),
                                '薪资范围': job.get('salaryDesc', ''),
                                '公司名称': job.get('brandName', ''),
                                '职位标签': ','.join(job.get('jobLabels', [])),
                                # skills 为列表接口里的短标签词，勿与侧栏「任职要求」长文混为一列
                                '技能关键词': ' '.join(job.get('skills', [])),
                                '职位要求': '',
                                '招聘人姓名': job.get('bossName', ''),
                                '招聘人职位': job.get('bossTitle', ''),
                                '公司行业': job.get('brandIndustry', ''),
                                '公司规模': job.get('brandScaleName', ''),
                                '职位描述': job.get('jobDesc', ''),
                                '岗位职责': '',
                                '任职要求': '',
                                '职位类别': job.get('jobType', ''),
                                '搜索关键词': keyword,
                                '搜索城市': self.city_name,
                                '数据年份': datetime.now().year,
                                '创建时间': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            
                            api_desc = self._list_api_job_description(job)
                            if api_desc:
                                job_info['职位描述'] = api_desc
                                d0, r0 = self._split_duty_and_requirement(api_desc)
                                if d0:
                                    job_info['岗位职责'] = d0
                                if r0:
                                    job_info['任职要求'] = r0
                            
                            # 右侧「岗位职责/任职资格」仅在点击左侧 div.job-info 后渲染，需 DOM 补全
                            try:
                                max_click = int(CRAWLER_CONFIG.get("detail_click_max_per_page", 15))
                                click_delay = float(CRAWLER_CONFIG.get("detail_click_delay_sec", 1.5))
                                if CRAWLER_CONFIG.get("fetch_detail_via_click", True) and idx < max_click:
                                    detail = self.click_and_get_detail(
                                        idx, job_id, job.get("jobName", "")
                                    )
                                    if detail:
                                        # 只合并正文，不把侧栏标签误写入「职位类别」
                                        for k in ("职位描述", "岗位职责", "任职要求"):
                                            v = detail.get(k)
                                            if v and str(v).strip():
                                                job_info[k] = str(v).strip()
                                        if job_info.get("任职要求"):
                                            job_info["职位要求"] = job_info["任职要求"]
                                        if (job_info.get("岗位职责") or job_info.get("任职要求")):
                                            print(f"    ✅ 职位 {idx+1} 侧栏职责/要求已写入")
                                        elif job_info.get("职位描述"):
                                            print(f"    ✅ 职位 {idx+1} 侧栏描述已写入")
                                        else:
                                            print(f"    ⚠️  职位 {idx+1} 侧栏未解析到文本（检查登录/页面）")
                                    else:
                                        print(f"    ⚠️  职位 {idx+1} 侧栏详情未取到")
                                    sleep(click_delay)
                            except Exception as e:
                                print(f"    ⚠️  职位 {idx+1} 侧栏补全异常: {e}")
                            
                            jobs.append(job_info)
                            page_jobs_count += 1
                            
                        except Exception as e:
                            print(f"    ⚠️  解析职位失败: {e}")
                        
                    print(f"  ✅ 第 {page + 1} 页采集完成，获取 {page_jobs_count} 条职位")
                    
                    # 检查中断标志（在每页处理完后检查）
                    if self.interrupted:
                        print(f"\n⚠️  检测到中断信号，停止采集...")
                        print(f"  📊 已收集 {len(jobs)} 条职位数据，准备返回...")
                        break
                    
                    # 5. 翻页与等待：避免请求过于频繁被反爬
                    if page < max_pages - 1:
                        print(f"  ⏳ 等待 {CRAWLER_CONFIG['request_delay']} 秒后继续...")
                        sleep(CRAWLER_CONFIG['request_delay'])
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"  ❌ 第 {page + 1} 页采集失败: {error_msg}")
                    
                    # 检查是否是连接断开错误
                    if '连接已断开' in error_msg or 'disconnected' in error_msg.lower():
                        print(f"  ⚠️  检测到连接断开，尝试重新初始化浏览器...")
                        try:
                            # 停止监听
                            try:
                                self.dp.listen.stop()
                            except:
                                pass
                            
                            # 重新初始化浏览器
                            self.close_browser()
                            sleep(2)
                            self.init_browser()
                            
                            url = self.geek_jobs_search_url(keyword, self.city_code)
                            self.dp.listen.start('joblist')
                            self.dp.get(url)
                            sleep(3)
                            
                            print(f"  ✅ 浏览器重新初始化完成，继续爬取...")
                        except Exception as reconnect_error:
                            print(f"  ❌ 重新初始化失败: {reconnect_error}")
                            # 如果重新初始化失败，返回已获取的数据
                            break
                    
                    # 继续下一页
                    if page < max_pages - 1:
                        sleep(2)
                    continue
            
        except KeyboardInterrupt:
            # Ctrl+C 不是 Exception，原逻辑不会走到 return jobs，导致总表始终为 0
            self.interrupted = True
            print(f"\n⚠️  用户中断关键词「{keyword}」：本关键词已采集 {len(jobs)} 条，将合并并保存")
            return jobs
        except Exception as e:
            error_msg = str(e)
            print(f"  ❌ 搜索失败 {keyword}: {error_msg}")
            
            # 检查是否是连接断开错误
            if '连接已断开' in error_msg or 'disconnected' in error_msg.lower():
                print(f"  ⚠️  检测到连接断开，尝试重新初始化浏览器...")
                try:
                    # 停止监听
                    try:
                        self.dp.listen.stop()
                    except:
                        pass
                    
                    # 重新初始化浏览器
                    self.close_browser()
                    sleep(2)
                    self.init_browser()
                    print(f"  ✅ 浏览器重新初始化完成")
                except Exception as reconnect_error:
                    print(f"  ❌ 重新初始化失败: {reconnect_error}")
        
        # 确保返回已获取的数据（即使有错误）
        return jobs
    
    def get_job_detail_by_js(self, job_id: str) -> Dict:
        """
        通过JavaScript直接从页面获取职位详情（更快的方法）
        """
        detail = {
            '职位描述': '',
            '岗位职责': '',
            '任职要求': '',
            '职位类别': ''
        }
        
        try:
            self.apply_desc_flex_for_full_text()
            # 侧栏 p.desc：与改 span 前一致用 innerText||textContent（自动化下 innerText 常为空）；再与 .job-recommend-result 等选择器取最长段
            js_primary = """
            (function(){
                function norm(s) {
                    if (!s) return '';
                    return String(s).replace(/^职位描述\\s*[\\n：:]/m, '').trim();
                }
                function collapseWs(s) {
                    return String(s || '').replace(/[ \\t\\f\\v]+/g, ' ').replace(/\\n\\s*\\n/g, '\\n').trim();
                }
                function textFromP(p) {
                    if (!p) return '';
                    return norm(collapseWs(String((p.innerText || p.textContent || '')).trim()));
                }
                var best = '';
                var roots = document.querySelectorAll('.job-detail-body');
                for (var r = 0; r < roots.length; r++) {
                    var nodes = roots[r].querySelectorAll('p.desc');
                    for (var i = 0; i < nodes.length; i++) {
                        var el = nodes[i];
                        if (el.closest && el.closest('.job-label-list')) continue;
                        var t = textFromP(el);
                        if (t.length > best.length) best = t;
                    }
                }
                var sels = [
                    '.job-detail-body p.desc',
                    '.job-detail-box .job-detail-body p.desc',
                    'div.job-detail-container .job-detail-body p.desc',
                    '.job-recommend-result p.desc',
                    '.page-jobs-main .job-recommend-result p.desc',
                    'p.desc'
                ];
                for (var j = 0; j < sels.length; j++) {
                    var el = document.querySelector(sels[j]);
                    if (!el) continue;
                    var t2 = textFromP(el);
                    if (t2.length > best.length) best = t2;
                }
                var all = document.querySelectorAll('p.desc');
                for (var k = 0; k < all.length; k++) {
                    var e = all[k];
                    if (e.closest && e.closest('.job-label-list')) continue;
                    var tk = textFromP(e);
                    if (tk.length > best.length) best = tk;
                }
                return best.length > 10 ? best : '';
            })();
            """
            # 对已定位的单个 p.desc：必须写成「function(元素){...}」；DrissionPage 默认会把其它脚本包一层 function(){...}，导致 IIFE 的 return 丢失且 arguments[0] 错位
            js_p_desc_plain = """function (p) {
                function norm(s) {
                    if (!s) return '';
                    return String(s).replace(/^职位描述\\s*[\\n：:]/m, '').trim();
                }
                function collapseWs(s) {
                    return String(s || '').replace(/[ \\t\\f\\v]+/g, ' ').replace(/\\n\\s*\\n/g, '\\n').trim();
                }
                if (!p) return '';
                return norm(collapseWs(String((p.innerText || p.textContent || '')).trim()));
            }"""
            try:
                primary_text = self.dp.run_js(js_primary.strip(), as_expr=True)
            except Exception:
                primary_text = None
            if primary_text is not None and not isinstance(primary_text, str):
                primary_text = str(primary_text)
            if primary_text is None:
                primary_text = ""
            primary_text = str(primary_text).strip()
            if len(primary_text) > 10:
                full = self._clean_side_panel_text(primary_text)
                if len(full) < 15:
                    full = unicodedata.normalize("NFKC", primary_text)
                if len(full) > 10:
                    detail["职位描述"] = full
                    duty, req = self._split_duty_and_requirement(full)
                    detail["岗位职责"] = (duty or full).strip()
                    if req:
                        detail["任职要求"] = req.strip()
                    print(f"    ✅ 侧栏正文: {full[:80]}...")
                    return detail
            
            # run_js 偶发拿不到时，对已定位的 p.desc 用 js_p_desc_plain
            try:
                for sel in (
                    "css:.job-recommend-result p.desc",
                    "css:.page-jobs-main p.desc",
                    "css:.job-detail-body p.desc",
                    "css:div.job-detail-body p.desc",
                ):
                    try:
                        el = self.dp.ele(sel, timeout=3)
                        if not el:
                            continue
                        raw = (self.dp.run_js(js_p_desc_plain, el) or "").strip()
                        if len(raw) < 12:
                            continue
                        full = self._clean_side_panel_text(raw)
                        if len(full) < 12:
                            full = unicodedata.normalize("NFKC", raw)
                        if len(full) > 10:
                            detail["职位描述"] = full
                            duty, req = self._split_duty_and_requirement(full)
                            detail["岗位职责"] = (duty or full).strip()
                            if req:
                                detail["任职要求"] = req.strip()
                            print(f"    ✅ 侧栏正文(DP): {full[:80]}...")
                            return detail
                    except Exception:
                        continue
                try:
                    body = (
                        self.dp.ele("css:.job-recommend-result", timeout=2)
                        or self.dp.ele("css:.page-jobs-main", timeout=2)
                        or self.dp.ele("css:div.job-detail-body", timeout=3)
                        or self.dp.ele("css:.job-detail-body", timeout=2)
                    )
                    if body:
                        pel = body.ele("css:p.desc", timeout=2)
                        if pel:
                            raw = (self.dp.run_js(js_p_desc_plain, pel) or "").strip()
                            if len(raw) >= 12:
                                full = self._clean_side_panel_text(raw)
                                if len(full) < 12:
                                    full = unicodedata.normalize("NFKC", raw)
                                if len(full) > 10:
                                    detail["职位描述"] = full
                                    duty, req = self._split_duty_and_requirement(full)
                                    detail["岗位职责"] = (duty or full).strip()
                                    if req:
                                        detail["任职要求"] = req.strip()
                                    print(f"    ✅ 侧栏正文(DP): {full[:80]}...")
                                    return detail
                except Exception:
                    pass
            except Exception:
                pass
            
            # 旧版布局：XPath 容器 + p.desc
            # 方法1：使用用户提供的XPath获取整个职位描述div
            try:
                # 获取整个职位描述div
                desc_div_xpath = '/html/body/div[1]/div[2]/div[3]/div/div/div[2]/div[1]/div'
                desc_div = self.dp.ele(f'xpath:{desc_div_xpath}', timeout=3)
                
                if desc_div:
                    # 在这个div中查找职位描述内容
                    # 1. 获取职位标签（job-label-list）
                    try:
                        label_list = desc_div.ele('css:.job-label-list', timeout=1)
                        if label_list:
                            labels = label_list.eles('tag:li')
                            if labels:
                                tag_texts = [li.text.strip() for li in labels if li.text and li.text.strip()]
                                if tag_texts:
                                    detail['职位类别'] = ','.join(tag_texts)
                                    print(f"    ✅ 获取到职位标签: {detail['职位类别']}")
                    except:
                        pass
                    
                    # 2. 获取职位描述：与 js_primary 相同，遍历全部 p.desc 取 innerText 最长（Vue 布局 XPath 易失效）
                    desc_text = None
                    try:
                        js_code = """
                        (function() {
                            function collapseWs(s) {
                                return String(s || '').replace(/[ \\t\\f\\v]+/g, ' ').replace(/\\n\\s*\\n/g, '\\n').trim();
                            }
                            var best = '';
                            var all = document.querySelectorAll('p.desc');
                            for (var i = 0; i < all.length; i++) {
                                var el = all[i];
                                if (el.closest && el.closest('.job-label-list')) continue;
                                var t = collapseWs(String((el.innerText || el.textContent || '')).trim());
                                if (t.length > best.length) best = t;
                            }
                            if (best.length > 5) {
                                best = best.replace(/\\.[a-zA-Z0-9_-]+\\s*\\{[^}]*\\}/g, '');
                                best = best.replace(/\\b(kanzhun|boss|直聘|BOSS)\\b/gi, '');
                                best = best.replace(/[ \\t]+/g, ' ').replace(/\\n\\s*\\n/g, '\\n').trim();
                                return best;
                            }
                            return '';
                        })();
                        """
                        desc_text = self.dp.run_js(js_code.strip(), as_expr=True)
                        if not isinstance(desc_text, str):
                            desc_text = ''
                        if len(desc_text.strip()) > 5:
                            detail['岗位职责'] = desc_text.strip()
                            detail['职位描述'] = desc_text.strip()
                            print(f"    ✅ 通过JavaScript innerText获取到职位描述: {desc_text[:100]}...")
                        else:
                            print(f"    ⚠️  JavaScript返回空或太短: {desc_text}")
                    except Exception as e:
                        print(f"    ⚠️  JavaScript获取失败: {e}")
                        import traceback
                        traceback.print_exc()
                    
                    # 方法A：直接使用XPath获取p标签（备用方案）
                    if not detail.get('岗位职责'):
                        try:
                            p_xpath = '/html/body/div[1]/div[2]/div[3]/div/div/div[2]/div[1]/div/p'
                            desc_p = self.dp.ele(f'xpath:{p_xpath}', timeout=2)
                            if desc_p:
                                try:
                                    desc_text = self.dp.run_js(js_p_desc_plain, desc_p)
                                    if isinstance(desc_text, str) and len(desc_text.strip()) > 5:
                                        detail['岗位职责'] = desc_text.strip()
                                        detail['职位描述'] = desc_text.strip()
                                        print(f"    ✅ 通过XPath+innerText获取到职位描述: {desc_text[:100]}...")
                                except:
                                    # 如果JavaScript失败，使用text属性并清理
                                    desc_text = desc_p.text
                                    if desc_text and len(desc_text.strip()) > 5:
                                        import re
                                        # 清理文本：移除CSS样式代码
                                        desc_text = re.sub(r'\.[a-zA-Z0-9_-]+\s*\{[^}]*\}', '', desc_text)
                                        # 移除干扰词（包括BOSS）
                                        desc_text = re.sub(r'\b(kanzhun|boss|直聘|BOSS)\b', '', desc_text, flags=re.IGNORECASE)
                                        # 清理空白
                                        desc_text = ' '.join(desc_text.split()).strip()
                                        if len(desc_text) > 5:
                                            detail['岗位职责'] = desc_text
                                            detail['职位描述'] = desc_text
                                            print(f"    ✅ 通过XPath获取到职位描述: {desc_text[:100]}...")
                        except Exception as e:
                            print(f"    ⚠️  直接XPath失败: {e}")
                    
                    # 方法B：在div容器中使用CSS选择器（备用方案2）
                    if not detail.get('岗位职责'):
                        try:
                            desc_p = desc_div.ele('css:p.desc', timeout=2)
                            if desc_p:
                                desc_text = self.dp.run_js(js_p_desc_plain, desc_p)
                                if isinstance(desc_text, str) and len(desc_text.strip()) > 5:
                                    # 清理文本（包括BOSS）
                                    import re
                                    desc_text = re.sub(r'\.[a-zA-Z0-9_-]+\s*\{[^}]*\}', '', desc_text)
                                    desc_text = re.sub(r'\b(kanzhun|boss|直聘|BOSS)\b', '', desc_text, flags=re.IGNORECASE)
                                    desc_text = ' '.join(desc_text.split()).strip()
                                    if len(desc_text) > 5:
                                        detail['岗位职责'] = desc_text
                                        detail['职位描述'] = desc_text
                                        print(f"    ✅ 通过CSS选择器获取到职位描述: {desc_text[:100]}...")
                        except Exception as e:
                            print(f"    ⚠️  CSS选择器失败: {e}")
                    
                    # 3. 尝试获取任职要求（可能在同一个div中，在职位描述之后）
                    # 查找"任职要求"标题
                    try:
                        req_title = desc_div.ele('text:任职要求', timeout=1)
                        if req_title:
                            # 找到任职要求标题后，获取其后的内容
                            # 方法A：获取父元素下的所有p标签（任职要求可能在下一个p标签中）
                            parent = req_title.parent()
                            if parent:
                                # 查找所有p标签，找到任职要求标题后的第一个p标签
                                all_p = parent.eles('tag:p')
                                for i, p in enumerate(all_p):
                                    if p.text and '任职要求' in p.text:
                                        # 找到任职要求标题，获取下一个p标签的内容
                                        if i + 1 < len(all_p):
                                            req_text = all_p[i + 1].text
                                            if req_text and len(req_text.strip()) > 5:
                                                detail['任职要求'] = ' '.join(req_text.split()).strip()
                                                print(f"    ✅ 获取到任职要求: {detail['任职要求'][:50]}...")
                                        break
                        else:
                            # 方法B：使用JavaScript在desc_div中查找"任职要求"
                            js_code = """function (descDiv) {
                                if (!descDiv) return '';
                                var fullText = descDiv.textContent || descDiv.innerText || '';
                                if (fullText.includes('任职要求')) {
                                    var parts = fullText.split('任职要求');
                                    if (parts.length > 1) {
                                        var reqPart = parts[1].split(/工作地址|公司地址|联系方式|查看更多/)[0].trim();
                                        return reqPart;
                                    }
                                }
                                return '';
                            }"""
                            req_text = self.dp.run_js(js_code, desc_div)
                            if req_text and isinstance(req_text, str) and len(req_text.strip()) > 5:
                                detail['任职要求'] = ' '.join(req_text.split()).strip()
                                print(f"    ✅ 通过JS获取到任职要求: {detail['任职要求'][:50]}...")
                    except:
                        pass
                    
            except Exception as e:
                print(f"    ⚠️  XPath获取失败: {e}")
                # 备用方案：使用CSS选择器
                try:
                    desc_p = self.dp.ele('css:p.desc', timeout=2)
                    if desc_p:
                        desc_text = desc_p.text
                        if desc_text and len(desc_text.strip()) > 5:
                            desc_text = ' '.join(desc_text.split())
                            detail['岗位职责'] = desc_text.strip()
                            detail['职位描述'] = desc_text.strip()
                            print(f"    ✅ 通过CSS选择器获取到职位描述: {desc_text[:100]}...")
                except:
                    pass
            
            # 方法2：使用JavaScript通过用户提供的XPath获取完整的职位描述（包括标签和编号列表）
            # 如果XPath方法没获取到或内容不够完整，使用JavaScript方法
            if not detail.get('岗位职责') or len(detail.get('岗位职责', '')) < 20:
                js_code = """
                (function() {
                    var detail = {
                        '职位描述': '',
                        '岗位职责': '',
                        '任职要求': '',
                        '职位类别': ''
                    };
                    (function fixDescFlex() {
                        var list = document.querySelectorAll('p.desc');
                        for (var k = 0; k < list.length; k++) {
                            var el = list[k];
                            el.style.setProperty('display', 'flex', 'important');
                            el.style.setProperty('flex-direction', 'column', 'important');
                            el.style.setProperty('overflow', 'visible', 'important');
                            el.style.setProperty('max-height', 'none', 'important');
                        }
                    })();
                    
                    // 方法1：使用用户提供的XPath获取职位描述
                    function getElementByXPath(path) {
                        return document.evaluate(path, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    }
                    
                    // 使用用户提供的XPath: /html/body/div[1]/div[2]/div[3]/div/div/div[2]/div[1]/div
                    // 这是整个职位描述的div容器
                    var descDiv = getElementByXPath('/html/body/div[1]/div[2]/div[3]/div/div/div[2]/div[1]/div');
                    
                    if (descDiv) {
                        // 1. 获取职位标签（job-label-list）
                        var labelList = descDiv.querySelector('.job-label-list');
                        if (labelList) {
                            var labels = labelList.querySelectorAll('li');
                            var tagTexts = [];
                            for (var i = 0; i < labels.length; i++) {
                                if (labels[i].textContent && labels[i].textContent.trim()) {
                                    tagTexts.push(labels[i].textContent.trim());
                                }
                            }
                            if (tagTexts.length > 0) {
                                detail['职位类别'] = tagTexts.join(',');
                            }
                        }
                        
                        // 2. 获取职位描述内容（p.desc）
                        var descP = descDiv.querySelector('p.desc');
                        if (descP && descP.textContent) {
                            // 清理文本：移除隐藏的span标签内容，只保留可见文本
                            // textContent会自动忽略隐藏元素，但innerText更可靠
                            var descText = descP.innerText || descP.textContent || '';
                            // 移除多余的空白字符，但保留换行
                            descText = descText.replace(/[\\s]+/g, ' ').trim();
                            
                            if (descText.length > 5) {
                                detail['岗位职责'] = descText;
                                detail['职位描述'] = descText;
                            }
                        }
                        
                        // 3. 获取任职要求（如果存在）
                        // 检查整个div中是否包含"任职要求"
                        var fullText = descDiv.textContent || descDiv.innerText || '';
                        if (fullText.includes('任职要求')) {
                            // 分离岗位职责和任职要求
                            var parts = fullText.split('任职要求');
                            if (parts.length > 1) {
                                // 获取任职要求部分（排除工作地址、公司地址等）
                                var reqPart = parts[1].split(/工作地址|公司地址|联系方式|查看更多|职位描述/)[0].trim();
                                // 清理文本
                                reqPart = reqPart.replace(/[\\s]+/g, ' ').trim();
                                if (reqPart.length > 5) {
                                    detail['任职要求'] = reqPart;
                                }
                            }
                        }
                    }
                    
                    // 方法2：查找"职位描述"标题下的所有内容（备用方案）
                    if (!detail['职位描述'] || detail['职位描述'].length < 20) {
                        var descTitle = null;
                        var allElements = document.querySelectorAll('*');
                        for (var i = 0; i < allElements.length; i++) {
                            var elem = allElements[i];
                            if (elem.textContent && elem.textContent.trim() === '职位描述') {
                                descTitle = elem;
                                break;
                            }
                        }
                        
                        if (descTitle) {
                            var parent = descTitle.parentElement;
                            if (parent) {
                                // 获取父元素下的所有文本内容
                                var descText = '';
                                var children = parent.querySelectorAll('p, div, ul, ol, li, span');
                                for (var j = 0; j < children.length; j++) {
                                    var child = children[j];
                                    if (child.textContent && child.textContent.trim().length > 5) {
                                        var childText = child.textContent.trim();
                                        if (childText !== '职位描述' && 
                                            !childText.includes('工作地址') && 
                                            !childText.includes('公司地址')) {
                                            descText += childText + '\\n';
                                        }
                                    }
                                }
                                if (descText) {
                                    detail['职位描述'] = descText.trim();
                                    detail['岗位职责'] = descText.trim();
                                }
                            }
                        }
                    }
                    
                    // 获取职位标签（如"功能测试"）
                    var tags = document.querySelectorAll('.job-tag, .tag, [class*="tag"], span[class*="tag"]');
                    var tagTexts = [];
                    for (var t = 0; t < tags.length; t++) {
                        var tag = tags[t];
                        if (tag.textContent && tag.textContent.trim()) {
                            var tagText = tag.textContent.trim();
                            // 排除一些常见的非标签文本
                            if (tagText.length < 20 && !tagText.includes('职位描述') && 
                                !tagText.includes('岗位职责') && !tagText.includes('任职要求')) {
                                tagTexts.push(tagText);
                            }
                        }
                    }
                    if (tagTexts.length > 0) {
                        detail['职位类别'] = tagTexts.join(',');
                    }
                    
                    return detail;
                })();
                """
                
                result = self.dp.run_js(js_code.strip(), as_expr=True)
                if result and isinstance(result, dict):
                    for key, value in result.items():
                        if value and isinstance(value, str) and len(value.strip()) > 5:
                            # 如果已有值，合并；如果没有，直接使用
                            if detail.get(key):
                                # 合并内容，避免重复
                                existing = detail[key]
                                if value.strip() not in existing:
                                    detail[key] = existing + '\\n' + value.strip()
                            else:
                                detail[key] = value.strip()
                
        except Exception as e:
            pass
        
        return detail
    
    def click_and_get_detail(self, job_index: int, job_id: str, job_name: str) -> Dict:
        """
        点击职位并获取详情
        """
        detail = {
            '职位描述': '',
            '岗位职责': '',
            '任职要求': '',
            '职位类别': ''
        }
        
        try:
            # Web 端 /web/geek/job 列表：需点击 li.job-card-box 内的 div.job-info 才会加载右侧详情
            click_target = None
            try:
                card_selectors = [
                    'css:ul.rec-job-list .job-card-wrap li.job-card-box',
                    'css:ul.rec-job-list li.job-card-box',
                    'css:.job-list-container ul.rec-job-list li.job-card-box',
                    'css:li.job-card-box',
                ]
                for cs in card_selectors:
                    try:
                        cards = self.dp.eles(cs, timeout=2)
                        if cards and job_index < len(cards):
                            t = cards[job_index].ele('css:div.job-info', timeout=2)
                            if t:
                                click_target = t
                                break
                    except Exception:
                        continue
            except Exception:
                pass
            
            if not click_target:
                job_selectors = [
                    'css:.job-card-wrapper',
                    'css:.job-list-box li',
                    'css:.job-primary',
                    'css:.job-item',
                    'tag:li'
                ]
                job_elem = None
                for selector in job_selectors:
                    try:
                        job_elements = self.dp.eles(selector, timeout=2)
                        if job_elements and job_index < len(job_elements):
                            job_elem = job_elements[job_index]
                            break
                    except Exception:
                        continue
                if job_elem:
                    try:
                        click_target = job_elem.ele('css:div.job-info', timeout=1) or job_elem
                    except Exception:
                        click_target = job_elem
            
            if click_target:
                click_target.click()
                sleep(1.5)
                # Vue 侧栏：详情 p.desc 可能在 .job-recommend-result，未必有 .job-detail-body
                for sel in (
                    "css:.job-recommend-result p.desc",
                    "css:.page-jobs-main p.desc",
                    "css:div.job-detail-body",
                    "css:.job-detail-body p.desc",
                    "css:.job-detail-box .job-detail-body",
                    "css:p.desc",
                ):
                    try:
                        self.dp.ele(sel, timeout=10)
                        break
                    except Exception:
                        continue
                sleep(1)
                self.apply_desc_flex_for_full_text()
                sleep(0.6)
                
                # 使用XPath直接获取详情
                detail = self.get_job_detail_by_js(job_id)
                
                # 如果XPath方法没获取到，再尝试其他方法
                if (
                    not detail.get("岗位职责")
                    and not detail.get("任职要求")
                    and not (detail.get("职位描述") or "").strip()
                ):
                    print(f"    ⚠️  get_job_detail_by_js未获取到，尝试get_job_detail_from_page...")
                    detail = self.get_job_detail_from_page(job_id, job_name)
                
        except Exception as e:
            pass
        
        return detail
    
    def get_job_detail_from_page(self, job_id: str, job_name: str) -> Dict:
        """
        从页面获取职位详细信息（岗位职责、任职要求等）
        :param job_id: 职位ID
        :param job_name: 职位名称
        :return: 详细信息字典
        """
        detail = {
            '职位描述': '',
            '岗位职责': '',
            '任职要求': '',
            '职位类别': ''
        }
        
        try:
            sleep(2)  # 等待详情面板加载
            
            # 方法1：使用JavaScript直接获取（最可靠）
            try:
                js_code = """
                (function() {
                    var result = {
                        '职位描述': '',
                        '岗位职责': '',
                        '任职要求': '',
                        '职位类别': ''
                    };
                    
                    // 查找所有可能的描述元素
                    var selectors = [
                        '.job-sec-text',
                        '.job-detail',
                        '.job-primary-detail',
                        '.job-box',
                        '.job-sec',
                        '[class*="job-detail"]',
                        '[class*="job-sec"]'
                    ];
                    
                    var fullText = '';
                    for (var i = 0; i < selectors.length; i++) {
                        var elems = document.querySelectorAll(selectors[i]);
                        if (elems.length > 0) {
                            elems.forEach(function(elem) {
                                if (elem.textContent && elem.textContent.trim().length > 20) {
                                    fullText += elem.textContent.trim() + '\\n\\n';
                                }
                            });
                            if (fullText.length > 50) break;
                        }
                    }
                    
                    if (fullText) {
                        result['职位描述'] = fullText.trim();
                        
                        // 分离岗位职责和任职要求
                        if (fullText.includes('岗位职责')) {
                            var parts = fullText.split('任职要求');
                            if (parts.length > 0) {
                                var duty = parts[0].replace(/岗位职责[：:]*/g, '').trim();
                                result['岗位职责'] = duty;
                            }
                            if (parts.length > 1) {
                                var req = parts[1].split(/工作地址|公司地址|联系方式/)[0].trim();
                                result['任职要求'] = req;
                            }
                        } else if (fullText.includes('职责')) {
                            // 如果没有明确的"岗位职责"标题，尝试提取职责部分
                            var dutyMatch = fullText.match(/职责[：:]*([\\s\\S]*?)(?:要求|任职|地址|联系方式|$)/);
                            if (dutyMatch) {
                                result['岗位职责'] = dutyMatch[1].trim();
                            }
                        }
                        
                        if (fullText.includes('任职要求')) {
                            var reqMatch = fullText.match(/任职要求[：:]*([\\s\\S]*?)(?:工作地址|公司地址|联系方式|$)/);
                            if (reqMatch) {
                                result['任职要求'] = reqMatch[1].trim();
                            }
                        }
                    }
                    
                    // 获取职位标签
                    var tagSelectors = ['.job-tag', '.tag-list .tag', '[class*="tag"]'];
                    var tags = [];
                    for (var i = 0; i < tagSelectors.length; i++) {
                        var tagElems = document.querySelectorAll(tagSelectors[i]);
                        if (tagElems.length > 0) {
                            tagElems.forEach(function(tag) {
                                if (tag.textContent && tag.textContent.trim()) {
                                    tags.push(tag.textContent.trim());
                                }
                            });
                            if (tags.length > 0) break;
                        }
                    }
                    if (tags.length > 0) {
                        result['职位类别'] = tags.join(',');
                    }
                    
                    return result;
                })();
                """
                
                js_result = self.dp.run_js(js_code.strip(), as_expr=True)
                if js_result and isinstance(js_result, dict):
                    # 清理和验证数据
                    for key, value in js_result.items():
                        if value and isinstance(value, str) and len(value.strip()) > 5:
                            detail[key] = value.strip()
                    
                    # 如果通过JS获取到了数据，直接返回
                    if detail.get('职位描述') or detail.get('岗位职责'):
                        return detail
            except Exception as e:
                pass
            
            # 方法2：使用DrissionPage的元素查找（备用）
            try:
                # 查找职位描述区域
                desc_selectors = [
                    'css:.job-sec-text',
                    'css:.job-detail',
                    'css:.job-primary-detail',
                    'css:.job-box',
                    'css:.job-sec'
                ]
                
                full_desc = ''
                for selector in desc_selectors:
                    try:
                        desc_elems = self.dp.eles(selector, timeout=1)
                        if desc_elems:
                            texts = [elem.text for elem in desc_elems if elem.text and len(elem.text.strip()) > 20]
                            if texts:
                                full_desc = '\n\n'.join(texts)
                                if len(full_desc) > 50:
                                    break
                    except:
                        continue
                
                if full_desc:
                    detail['职位描述'] = full_desc
                    
                    # 分离岗位职责和任职要求
                    if '岗位职责' in full_desc:
                        parts = full_desc.split('任职要求')
                        if len(parts) > 0:
                            duty_part = parts[0].replace('岗位职责', '').replace('：', '').replace(':', '').strip()
                            detail['岗位职责'] = duty_part
                        if len(parts) > 1:
                            req_part = parts[1].split('工作地址')[0].split('公司地址')[0].strip()
                            detail['任职要求'] = req_part
                    elif '职责' in full_desc and '任职要求' in full_desc:
                        # 尝试提取职责部分
                        import re
                        duty_match = re.search(r'职责[：:]?([\s\S]*?)任职要求', full_desc)
                        if duty_match:
                            detail['岗位职责'] = duty_match.group(1).strip()
                        
                        req_match = re.search(r'任职要求[：:]?([\s\S]*?)(?:工作地址|公司地址|联系方式|$)', full_desc)
                        if req_match:
                            detail['任职要求'] = req_match.group(1).strip()
                
            except Exception as e:
                pass
            
            # 方法3：获取职位标签
            try:
                tag_elems = self.dp.eles('css:.job-tag', timeout=1)
                if not tag_elems:
                    tag_elems = self.dp.eles('css:.tag', timeout=1)
                
                if tag_elems:
                    tags = [elem.text for elem in tag_elems if elem.text and elem.text.strip()]
                    if tags:
                        detail['职位类别'] = ','.join(tags)
            except:
                pass
            
        except Exception as e:
            pass
        
        return detail
    
    def extract_jobs_from_dom(self) -> List[Dict]:
        """
        从页面DOM直接提取职位数据（备用方案）
        当API监听失败时使用
        """
        jobs = []
        try:
            # 检查当前页面是否是搜索页（更精确的检测）
            try:
                current_url = self.dp.url
                # 只检测明确的跳转（wuhan/?ka=header-home）
                if 'wuhan' in current_url and '/?ka=header' in current_url:
                    print(f"  ⚠️  当前页面不是搜索页（URL: {current_url}），无法提取数据")
                    return jobs
            except:
                pass
            
            # 查找职位列表元素
            # 尝试多种选择器
            job_elements = []
            selectors = [
                'css:ul.rec-job-list li.job-card-box',
                'css:li.job-card-box',
                'css:.job-card-wrapper',
                'css:.job-list-box li',
                'css:.job-primary',
                'css:.job-item',
                'tag:li'
            ]
            
            for selector in selectors:
                try:
                    elements = self.dp.eles(selector, timeout=2)
                    if elements and len(elements) > 0:
                        job_elements = elements
                        print(f"  💡 使用选择器 '{selector}' 找到 {len(job_elements)} 个职位元素")
                        break
                except Exception:
                    continue
            
            if not job_elements:
                print(f"  ⚠️  未找到职位元素，可能页面结构不同或页面未加载完成")
                return jobs
            
            print(f"  💡 从DOM找到 {len(job_elements)} 个职位元素，开始提取...")
            
            extracted_count = 0
            for idx, elem in enumerate(job_elements[:30]):  # 限制数量，避免过多
                try:
                    # 提取职位名称（尝试多种选择器）
                    job_name = ''
                    job_name_selectors = ['css:.job-name', 'css:.job-title', 'css:a[ka*="job"]', 'tag:a']
                    for sel in job_name_selectors:
                        try:
                            job_name_elem = elem.ele(sel, timeout=0.3)
                            if job_name_elem:
                                job_name = job_name_elem.text.strip()
                                if job_name and len(job_name) > 1:
                                    break
                        except Exception:
                            continue
                    
                    if not job_name or len(job_name) < 2:
                        try:
                            ji = elem.ele('css:div.job-info', timeout=0.3)
                            if ji and ji.text:
                                raw = ji.text.strip()
                                job_name = raw.split()[0] if raw.split() else raw[:24]
                        except Exception:
                            pass
                    
                    if not job_name or len(job_name) < 2:
                        continue
                    
                    # 提取公司名称
                    company_name = ''
                    company_selectors = ['css:.company-name', 'css:.company-text', 'css:.brand-name']
                    for sel in company_selectors:
                        try:
                            company_elem = elem.ele(sel, timeout=0.3)
                            if company_elem:
                                company_name = company_elem.text.strip()
                                if company_name:
                                    break
                        except:
                            continue
                    
                    # 提取薪资
                    salary = ''
                    try:
                        salary_elem = elem.ele('css:.salary', timeout=0.3)
                        if salary_elem:
                            salary = salary_elem.text.strip()
                    except:
                        pass
                    
                    # 提取地点
                    location = ''
                    location_selectors = ['css:.job-area', 'css:.job-location', 'css:.area']
                    for sel in location_selectors:
                        try:
                            location_elem = elem.ele(sel, timeout=0.3)
                            if location_elem:
                                location = location_elem.text.strip()
                                if location:
                                    break
                        except:
                            continue
                    
                    # 提取经验要求
                    experience = ''
                    try:
                        exp_elem = elem.ele('css:.job-limit', timeout=0.3)
                        if exp_elem:
                            experience = exp_elem.text.strip()
                    except:
                        pass
                    
                    # 生成职位ID
                    job_id = f"{job_name}_{company_name}_{location}"
                    if not job_id or job_id == '__':
                        job_id = f"dom_{idx}_{len(jobs)}"
                    
                    job_info = {
                        '职位ID': job_id,
                        '岗位名称': job_name,
                        '公司名称': company_name,
                        '薪资范围': salary,
                        '工作地点': location,
                        '工作经验': experience,
                        '职位描述': '',  # DOM提取可能没有详细信息
                        '岗位职责': '',
                        '任职要求': '',
                        '搜索关键词': '',
                        '数据年份': datetime.now().year,
                        '创建时间': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    jobs.append(job_info)
                    extracted_count += 1
                    
                except Exception as e:
                    continue
            
            print(f"  ✅ DOM提取完成，成功提取 {extracted_count} 条职位数据")
                    
        except Exception as e:
            print(f"  ⚠️  DOM提取失败: {e}")
            import traceback
            traceback.print_exc()
        
        return jobs
    
    def search_jobs_by_clicking(self, keyword: str, max_pages: int = 10) -> List[Dict]:
        """
        通过点击列表页职位项获取详情（模拟人工操作）
        :param keyword: 搜索关键词
        :param max_pages: 最大爬取页数
        :return: 职位列表
        """
        jobs = []
        local_seen_ids = set()
        list_page_url = None
        
        try:
            # 1. 访问搜索列表页（与站点一致 /web/geek/jobs，query 已编码）
            url = self.geek_jobs_search_url(keyword, self.city_code)
            print(f"  📍 访问列表页: {url}")
            
            # 检查当前页面，如果已跳转，先访问首页
            try:
                current_url = self.dp.url
                if 'jobs?ka=header' in current_url or ('wuhan' in current_url and '/?ka=' in current_url):
                    print(f"  ⚠️  当前页面已跳转，先访问首页...")
                    self.dp.get('https://www.zhipin.com')
                    sleep(3)
            except:
                pass
            
            # 访问搜索页
            self.dp.get(url)
            sleep(5)  # 等待页面加载
            self._scroll_list_page()
            sleep(2)  # Vue 渲染职位卡片后再取 div.job-info
            
            # 检查是否需要登录
            if not self.check_login_status():
                print(f"  ⚠️  需要登录")
                self.wait_for_login()
                self.dp.get(url)
                sleep(5)
            
            # 保存列表页URL，用于返回
            list_page_url = self.dp.url
            print(f"  ✅ 列表页加载完成: {list_page_url}")
            
            # 2. 循环处理每一页
            for page in range(max_pages):
                if self.interrupted:
                    print(f"\n⚠️  检测到中断信号，停止爬取...")
                    break
                
                print(f"\n  📄 正在处理第 {page + 1} 页...")
                
                # 确保在列表页（/web/geek/jobs 无 'job?' 子串，必须用路径判断）
                if not self._is_geek_job_search_page(self.dp.url):
                    print(f"  ⚠️  不在列表页，返回列表页...")
                    if list_page_url:
                        self.dp.get(list_page_url)
                        sleep(3)
                    else:
                        self.dp.get(url)
                        sleep(3)
                
                # 3. 获取当前页的所有职位链接
                job_links = self._get_job_links_from_list()
                
                if not job_links:
                    print(f"  ⚠️  第 {page + 1} 页未找到职位链接，尝试滚动刷新...")
                    self._scroll_list_page()
                    sleep(2)
                    job_links = self._get_job_links_from_list()
                
                if not job_links:
                    print(f"  ❌ 第 {page + 1} 页未找到职位，可能已到最后一页")
                    break
                
                print(f"  💡 找到 {len(job_links)} 个职位链接")
                
                # 4. 循环点击每个职位获取详情
                for idx, job_link in enumerate(job_links):
                    if self.interrupted:
                        break
                    
                    try:
                        print(f"    [{idx+1}/{len(job_links)}] 正在处理职位...")
                        
                        # 确保在列表页
                        if not self._is_geek_job_search_page(self.dp.url):
                            if list_page_url:
                                self.dp.get(list_page_url)
                                sleep(2)
                            else:
                                self.dp.get(url)
                                sleep(2)
                            # 重新获取链接（页面可能已刷新）
                            job_links = self._get_job_links_from_list()
                            if idx < len(job_links):
                                job_link = job_links[idx]
                            else:
                                print(f"    ⚠️  链接索引超出范围，跳过")
                                break
                        
                        # 点击职位链接
                        job_info = self._click_job_and_get_detail(job_link, keyword)
                        
                        if job_info:
                            job_id = job_info.get('职位ID', '')
                            if job_id and job_id not in local_seen_ids:
                                local_seen_ids.add(job_id)
                                jobs.append(job_info)
                                print(f"    ✅ 获取到职位: {job_info.get('岗位名称', 'N/A')}")
                            else:
                                print(f"    ⚠️  职位已存在或ID为空，跳过")
                        
                        # 独立详情页需后退；/web/geek/job 侧栏模式未离开列表，禁止后退以免离开站点
                        sleep(0.5)
                        cur_after = self.dp.url or ''
                        if 'zhipin.com/web/geek/job' in cur_after and 'job_detail' not in cur_after:
                            pass
                        else:
                            try:
                                self.dp.back()
                                sleep(2)
                                current_url = self.dp.url
                                still_detail = 'job_detail' in current_url or (
                                    '/job/' in current_url and 'web/geek/job' not in current_url
                                )
                                if still_detail:
                                    if list_page_url:
                                        self.dp.get(list_page_url)
                                        sleep(2)
                                    else:
                                        self.dp.get(url)
                                        sleep(2)
                            except Exception:
                                if list_page_url:
                                    self.dp.get(list_page_url)
                                    sleep(2)
                                else:
                                    self.dp.get(url)
                                    sleep(2)
                        
                    except Exception as e:
                        print(f"    ❌ 处理职位时出错: {e}")
                        # 尝试返回列表页
                        try:
                            if list_page_url:
                                self.dp.get(list_page_url)
                                sleep(2)
                        except:
                            pass
                        continue
                
                # 5. 滚动到页面底部，触发加载更多或翻页
                print(f"  📜 滚动列表页以加载更多数据...")
                self._scroll_list_page()
                sleep(2)
                
                # 6. 尝试点击"下一页"按钮
                next_page_clicked = self._click_next_page()
                if not next_page_clicked:
                    print(f"  ⚠️  未找到下一页按钮，可能已到最后一页")
                    # 尝试滚动加载更多
                    self._scroll_list_page()
                    sleep(2)
                    # 检查是否有新数据加载
                    new_links = self._get_job_links_from_list()
                    if len(new_links) <= len(job_links):
                        print(f"  ✅ 已到最后一页")
                        break
                
                # 更新列表页URL（可能已翻页）
                list_page_url = self.dp.url
                
                # 避免请求过快
                if page < max_pages - 1:
                    sleep(CRAWLER_CONFIG.get('request_delay', 3))
            
            print(f"  ✅ 通过点击方式完成爬取，共获取 {len(jobs)} 条职位")
            
        except KeyboardInterrupt:
            print(f"\n⚠️  用户中断")
            self.interrupted = True
        except Exception as e:
            print(f"  ❌ 爬取过程出错: {e}")
            import traceback
            traceback.print_exc()
        
        return jobs
    
    def _get_job_links_from_list(self) -> List:
        """
        从列表页获取所有职位链接元素
        :return: 职位链接元素列表
        """
        job_links = []
        
        try:
            # Web 端列表为 SPA：点击 li.job-card-box 内 div.job-info 才加载右侧详情（无独立 href）
            job_info_selectors = [
                'css:ul.rec-job-list li.job-card-box div.job-info',
                'css:.job-list-container li.job-card-box div.job-info',
                'css:.recommend-result-job li.job-card-box div.job-info',
                'css:.page-job-main li.job-card-box div.job-info',
                'css:li.job-card-box div.job-info',
                'css:div[class*="job-card-box"] div.job-info',
            ]
            for selector in job_info_selectors:
                try:
                    elements = self.dp.eles(selector, timeout=2)
                    if elements:
                        for elem in elements:
                            try:
                                if elem and (elem.text or '').strip():
                                    if elem not in job_links:
                                        job_links.append(elem)
                            except Exception:
                                continue
                        if job_links:
                            print(f"    💡 使用选择器 '{selector}' 找到 {len(job_links)} 个 job-info 可点击项")
                            break
                except Exception:
                    continue
            
            if not job_links:
                # 尝试多种选择器查找职位链接（旧版列表或跳转详情页）
                selectors = [
                    'css:.job-card-wrapper a',
                    'css:.job-list-box li a',
                    'css:.job-primary a',
                    'css:.job-item a',
                    'css:a[ka*="job"]',
                    'xpath://li[contains(@class, "job")]//a'
                ]
                
                for selector in selectors:
                    try:
                        elements = self.dp.eles(selector, timeout=2)
                        if elements:
                            for elem in elements:
                                try:
                                    href = elem.attr('href') or ''
                                    text = elem.text or ''
                                    if ('job_detail' in href or '/job/' in href) and text.strip():
                                        if elem not in job_links:
                                            job_links.append(elem)
                                except Exception:
                                    continue
                            
                            if job_links:
                                print(f"    💡 使用选择器 '{selector}' 找到 {len(job_links)} 个职位链接")
                                break
                    except Exception:
                        continue
            
            # 去重（基于href）
            seen_hrefs = set()
            unique_links = []
            for link in job_links:
                try:
                    href = link.attr('href') or ''
                    if href and href not in seen_hrefs:
                        seen_hrefs.add(href)
                        unique_links.append(link)
                except:
                    continue
            
            return unique_links[:30]  # 限制数量，避免过多
            
        except Exception as e:
            print(f"    ⚠️  获取职位链接失败: {e}")
            return []
    
    def _click_job_and_get_detail(self, job_link, keyword: str) -> Optional[Dict]:
        """
        点击列表项以加载详情（div.job-info 或 <a> 职位链接）
        :param job_link: 可点击元素（优先 li.job-card-box 内 div.job-info）
        :param keyword: 搜索关键词
        :return: 职位信息字典
        """
        try:
            job_name = ''
            company_name = ''
            salary = ''
            location = ''
            
            is_job_info = False
            try:
                cls = (job_link.attr('class') or '')
                tag = (job_link.tag or '').lower() if getattr(job_link, 'tag', None) else ''
                is_job_info = tag == 'div' and 'job-info' in cls
            except Exception:
                pass
            
            try:
                if is_job_info:
                    raw = (job_link.text or '').strip()
                    card = self._find_job_card_root(job_link)
                    if card:
                        for sel in ('css:.job-name', 'css:.job-title', 'css:.name', 'css:h3', 'css:a'):
                            try:
                                ne = card.ele(sel, timeout=0.5)
                                if ne and (ne.text or '').strip():
                                    job_name = (ne.text or '').strip()
                                    break
                            except Exception:
                                continue
                        if not job_name and raw:
                            job_name = raw.split()[0] if raw.split() else raw[:32]
                        for sel in ('css:.company-name', 'css:.company-text', 'css:.brand-name', 'css:.company'):
                            try:
                                ce = card.ele(sel, timeout=0.5)
                                if ce and (ce.text or '').strip():
                                    company_name = (ce.text or '').strip()
                                    break
                            except Exception:
                                continue
                        for sel in ('css:.salary',):
                            try:
                                se = card.ele(sel, timeout=0.5)
                                if se and (se.text or '').strip():
                                    salary = (se.text or '').strip()
                                    break
                            except Exception:
                                pass
                        for sel in ('css:.job-area', 'css:.job-location', 'css:.area'):
                            try:
                                le = card.ele(sel, timeout=0.5)
                                if le and (le.text or '').strip():
                                    location = (le.text or '').strip()
                                    break
                            except Exception:
                                pass
                    else:
                        job_name = raw.split()[0] if raw and raw.split() else raw[:32]
                else:
                    job_name = job_link.text.strip() if job_link.text else ''
                    parent = job_link.parent()
                    if parent:
                        company_elem = parent.ele('css:.company-name', timeout=1)
                        if not company_elem:
                            company_elem = parent.ele('css:.company-text', timeout=1)
                        if company_elem:
                            company_name = company_elem.text.strip() if company_elem.text else ''
                        salary_elem = parent.ele('css:.salary', timeout=1)
                        if salary_elem:
                            salary = salary_elem.text.strip() if salary_elem.text else ''
                        location_elem = parent.ele('css:.job-area', timeout=1)
                        if not location_elem:
                            location_elem = parent.ele('css:.job-location', timeout=1)
                        if location_elem:
                            location = location_elem.text.strip() if location_elem.text else ''
            except Exception:
                pass
            
            print(f"      🔗 点击职位: {job_name[:30] if job_name else 'N/A'}...")
            job_link.click()
            sleep(3)
            
            current_url = self.dp.url or ''
            spa_list = 'zhipin.com/web/geek/job' in current_url and 'job_detail' not in current_url
            has_detail_url = 'job_detail' in current_url or '/job/' in current_url
            
            if spa_list or has_detail_url:
                try:
                    for _sel in ('css:.job-recommend-result p.desc', 'css:.page-jobs-main p.desc', 'css:p.desc'):
                        try:
                            self.dp.ele(_sel, timeout=8)
                            break
                        except Exception:
                            continue
                except Exception:
                    pass
                self.apply_desc_flex_for_full_text()
            else:
                try:
                    for _sel in ('css:.job-recommend-result p.desc', 'css:.page-jobs-main p.desc', 'css:p.desc'):
                        try:
                            self.dp.ele(_sel, timeout=6)
                            break
                        except Exception:
                            continue
                    self.apply_desc_flex_for_full_text()
                except Exception:
                    print(f"      ⚠️  未进入详情侧栏/详情页，当前URL: {current_url}")
                    return None
            
            job_id = ''
            try:
                if '/job_detail/' in current_url:
                    parts = current_url.split('/job_detail/')
                    if len(parts) > 1:
                        job_id = parts[1].split('.')[0].split('?')[0]
                elif '/job/' in current_url:
                    parts = current_url.split('/job/')
                    if len(parts) > 1:
                        job_id = parts[1].split('/')[0].split('?')[0]
            except Exception:
                pass
            
            if not job_id:
                job_id = f"{job_name}_{company_name}_{location}" if job_name else f"job_{len(self.all_jobs)}"
            
            detail = self.get_job_detail_by_js(job_id)
            if not detail.get('职位描述') and not detail.get('岗位职责'):
                detail = self.get_job_detail_from_page(job_id, job_name)
            
            # 构建完整的职位信息
            req_text = (detail.get('任职要求') or '').strip()
            job_info = {
                '职位ID': job_id,
                '岗位名称': job_name or detail.get('岗位名称', ''),
                '公司名称': company_name or detail.get('公司名称', ''),
                '薪资范围': salary or detail.get('薪资范围', ''),
                '工作地点': location or detail.get('工作地点', ''),
                '职位描述': detail.get('职位描述', ''),
                '岗位职责': detail.get('岗位职责', ''),
                '任职要求': req_text,
                '职位要求': req_text,
                '技能关键词': '',
                '职位类别': detail.get('职位类别', ''),
                '搜索关键词': keyword,
                '数据年份': datetime.now().year,
                '创建时间': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            return job_info
            
        except Exception as e:
            print(f"      ❌ 点击职位获取详情失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _scroll_list_page(self):
        """
        滚动列表页以触发加载更多数据
        """
        try:
            # 滚动到页面底部
            scroll_js = """
            (function() {
                window.scrollTo(0, document.body.scrollHeight);
                return true;
            })();
            """
            self.dp.run_js(scroll_js)
            sleep(1)
            
            # 再滚动一点，确保触发加载
            scroll_js2 = """
            (function() {
                window.scrollBy(0, 500);
                return true;
            })();
            """
            self.dp.run_js(scroll_js2)
            sleep(1)
            
        except Exception as e:
            print(f"    ⚠️  滚动失败: {e}")
    
    def _click_next_page(self) -> bool:
        """
        点击"下一页"按钮
        :return: 是否成功点击
        """
        try:
            # 尝试多种选择器查找"下一页"按钮
            next_selectors = [
                'css:.pager a:last-child',
                'css:.pagination .next',
                'css:.page-next',
                'text:下一页',
                'text:>',
                'xpath://a[contains(text(), "下一页")]',
                'xpath://a[contains(@class, "next")]'
            ]
            
            for selector in next_selectors:
                try:
                    next_btn = self.dp.ele(selector, timeout=2)
                    if next_btn:
                        # 检查按钮是否可点击（不是disabled）
                        try:
                            if 'disabled' not in (next_btn.attr('class') or ''):
                                print(f"    ➡️  找到下一页按钮，点击...")
                                next_btn.click()
                                sleep(3)  # 等待页面加载
                                return True
                        except:
                            pass
                except:
                    continue
            
            return False
            
        except Exception as e:
            print(f"    ⚠️  查找下一页按钮失败: {e}")
            return False
    
    def crawl_all_ict_jobs(self, max_pages_per_keyword: int = 10, output_file: Optional[str] = None):
        """
        爬取所有ICT相关职位（全国搜索）
        :param max_pages_per_keyword: 每个关键词的最大页数
        :param output_file: 输出文件名（默认自动生成）
        """
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.output_dir / f"ict_jobs_全国_{timestamp}.xlsx"
        
        print("🚀 开始初始化浏览器...")
        self.init_browser()
        
        # 检查初始化后的页面状态
        try:
            init_url = self.dp.url
            print(f"  💡 初始化后页面URL: {init_url}")
            if 'jobs?ka=header' in init_url:
                print(f"  ⚠️  初始化后检测到跳转，访问首页...")
                self.dp.get('https://www.zhipin.com')
                sleep(3)
        except Exception as e:
            print(f"  ⚠️  检查初始化URL时出错: {e}")
        
        try:
            total_keywords = len(self.ict_keywords)
            
            print(f"\n{'='*60}")
            print(f"📊 开始爬取全国ICT相关职位")
            print(f"📌 关键词数量: {total_keywords}")
            print(f"📌 每个关键词爬取: {max_pages_per_keyword} 页")
            print(f"📁 输出文件: {output_file}")
            print(f"{'='*60}\n")
            
            for idx, keyword in enumerate(self.ict_keywords, 1):
                # 检查中断标志
                if self.interrupted:
                    print(f"\n⚠️  检测到中断信号，停止爬取...")
                    break
                
                print(f"\n[{idx}/{total_keywords}] 搜索关键词: {keyword}")
                print("-" * 60)
                
                try:
                    # 检查浏览器连接状态和当前页面
                    try:
                        current_url = self.dp.url
                        print(f"  💡 当前页面URL: {current_url}")
                        # 检查是否跳转到非搜索页面（更精确的检测）
                        is_redirected = False
                        if 'jobs?ka=header' in current_url:
                            is_redirected = True
                            print(f"  ⚠️  检测到跳转到 jobs?ka=header-jobs")
                        elif 'wuhan' in current_url and '/?ka=' in current_url:
                            is_redirected = True
                            print(f"  ⚠️  检测到跳转到 wuhan/?ka= (可能是 header-home 或其他)")
                        elif 'gongsi' in current_url or 'company' in current_url:
                            is_redirected = True
                            print(f"  ⚠️  检测到跳转到公司页面")
                        elif 'school/?ka=' in current_url:
                            is_redirected = True
                            print(f"  ⚠️  检测到跳转到 school/?ka=tab_school_recruit_click")
                        
                        if is_redirected:
                            print(f"  ⚠️  检测到页面跳转，重新访问搜索页...")
                            # 先访问首页，再访问搜索页
                            self.dp.get('https://www.zhipin.com')
                            sleep(3)
                            search_url = self.geek_jobs_search_url(keyword, self.city_code)
                            self.dp.get(search_url)
                            sleep(5)
                            # 再次检查
                            current_url = self.dp.url
                            if 'jobs?ka=header' in current_url or ('wuhan' in current_url and '/?ka=' in current_url) or 'gongsi' in current_url or 'company' in current_url or 'school/?ka=' in current_url:
                                print(f"  ❌ 页面仍然跳转，可能被重定向，跳过此关键词")
                                continue
                            else:
                                print(f"  ✅ 重新访问成功，当前URL: {current_url}")
                    except Exception as url_check_error:
                        print(f"  ⚠️  检查URL失败: {url_check_error}，继续尝试搜索...")
                    
                    # 根据配置选择使用点击模式或API监听模式
                    if self.use_click_mode:
                        jobs = self.search_jobs_by_clicking(keyword, max_pages=max_pages_per_keyword)
                    else:
                        jobs = self.search_jobs_by_keyword(keyword, max_pages=max_pages_per_keyword)
                    
                    # 无论是否中断，都要处理已获取的数据
                    new_jobs = 0
                    if jobs and len(jobs) > 0:
                        print(f"  📊 本次搜索获取到 {len(jobs)} 条职位数据，开始添加到总列表...")
                        for job in jobs:
                            # 再次去重（防止不同关键词搜索到相同职位）
                            job_id = job.get('职位ID', '')
                            if not job_id or job_id == '':
                                # 如果职位ID为空，生成一个
                                job_id = f"{job.get('岗位名称', '')}_{job.get('公司名称', '')}_{job.get('城市', '')}"
                            
                            if job_id and job_id not in self.seen_job_ids:
                                self.seen_job_ids.add(job_id)
                                self.all_jobs.append(job)
                                new_jobs += 1
                            else:
                                # 调试：显示为什么被去重
                                if job_id in self.seen_job_ids:
                                    pass  # 正常去重，不打印
                        print(f"  ✅ 已将 {new_jobs} 条新职位添加到总列表（当前总计: {len(self.all_jobs)} 条）")
                    else:
                        print(f"  ⚠️  本次搜索未获取到数据（jobs为空或长度为0）")
                    
                    print(f"  ✅ 新增 {new_jobs} 条不重复职位（总计: {len(self.all_jobs)} 条）")
                    
                    # 调试信息：显示去重情况
                    if jobs and new_jobs == 0:
                        print(f"  ⚠️  警告：获取了 {len(jobs)} 条数据，但新增为0，可能所有数据都是重复的")
                        # 显示前3条数据的ID
                        for i, job in enumerate(jobs[:3]):
                            print(f"    示例数据 {i+1}: ID={job.get('职位ID', 'N/A')[:50]}, 职位={job.get('岗位名称', 'N/A')[:30]}")
                    
                    # 每个关键词完成后都保存数据（防止丢失）
                    if len(self.all_jobs) > 0:
                        try:
                            self.save_to_excel(output_file)
                            print(f"  💾 数据已保存到: {output_file}（当前{len(self.all_jobs)}条）")
                        except Exception as save_error:
                            print(f"  ⚠️  保存数据失败: {save_error}")
                            import traceback
                            traceback.print_exc()
                    else:
                        print(f"  ⚠️  当前没有数据需要保存（all_jobs为空）")
                    
                    # 定期保存（每30条）
                    save_interval = CRAWLER_CONFIG.get('save_interval', 30)
                    if len(self.all_jobs) > 0 and len(self.all_jobs) % save_interval == 0:
                        try:
                            self.save_to_excel(output_file)
                            print(f"  💾 定期保存: 已累计 {len(self.all_jobs)} 条数据（每{save_interval}条保存一次）")
                        except Exception as save_error:
                            print(f"  ⚠️  定期保存失败: {save_error}")
                    
                    if self.interrupted:
                        print(f"  ⚠️  已中断，不再爬取后续关键词")
                        break
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"  ❌ 关键词 '{keyword}' 爬取失败: {error_msg}")
                    
                    # 即使出错也保存已收集的数据
                    if len(self.all_jobs) > 0:
                        try:
                            self.save_to_excel(output_file)
                            print(f"  💾 出错前保存已收集的数据: {output_file}（{len(self.all_jobs)}条）")
                        except:
                            pass
                    
                    # 检查是否是连接断开错误
                    if '连接已断开' in error_msg or 'disconnected' in error_msg.lower():
                        print(f"  ⚠️  检测到连接断开，尝试重新初始化浏览器...")
                        try:
                            self.close_browser()
                            sleep(2)
                            self.init_browser()
                            print(f"  ✅ 浏览器重新初始化完成，继续下一个关键词")
                        except Exception as reconnect_error:
                            print(f"  ❌ 重新初始化失败: {reconnect_error}")
                            # 如果重新初始化失败，继续下一个关键词（不中断整个流程）
                    
                    # 继续下一个关键词（不中断整个流程）
                    print(f"  ⏭️  跳过此关键词，继续下一个...")
                
                # 避免请求过快
                if idx < total_keywords:
                    print(f"  ⏳ 等待 {CRAWLER_CONFIG['request_delay']} 秒后继续下一个关键词...")
                    sleep(CRAWLER_CONFIG['request_delay'])
            
            # 最终保存
            self.save_to_excel(output_file)
            
            print(f"\n{'='*60}")
            print(f"✅ 爬取完成！")
            print(f"📊 共获取 {len(self.all_jobs)} 条不重复职位")
            print(f"📁 数据已保存到: {output_file}")
            print(f"{'='*60}\n")
            
        except KeyboardInterrupt:
            print("\n\n⚠️  用户中断爬取（KeyboardInterrupt）")
            self.interrupted = True
            print(f"📊 当前已收集 {len(self.all_jobs)} 条数据")
            if len(self.all_jobs) > 0:
                try:
                    print(f"💾 正在保存数据到: {output_file}")
                    self.save_to_excel(output_file)
                    print(f"✅ 已保存 {len(self.all_jobs)} 条数据到 {output_file}")
                except Exception as save_err:
                    print(f"❌ 保存数据时出错: {save_err}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"⚠️  没有数据需要保存（all_jobs为空）")
        except Exception as e:
            print(f"\n❌ 爬取过程出错: {e}")
            import traceback
            traceback.print_exc()
            if self.all_jobs:
                try:
                    self.save_to_excel(output_file)
                    print(f"💾 已保存 {len(self.all_jobs)} 条数据到 {output_file}")
                except Exception as save_err:
                    print(f"⚠️  保存数据时出错: {save_err}")
        finally:
            # 确保浏览器关闭
            if self.dp:
                try:
                    print("🔒 正在关闭浏览器...")
                    self.dp.quit()
                except Exception as quit_err:
                    print(f"⚠️  关闭浏览器时出错: {quit_err}")
                    # 尝试强制关闭
                    try:
                        if hasattr(self.dp, 'close'):
                            self.dp.close()
                    except:
                        pass
    
    def save_to_excel(self, output_file: str):
        """保存到Excel文件"""
        if not self.all_jobs:
            print(f"  ⚠️  没有数据需要保存（all_jobs为空，共0条）")
            return
        
        try:
            # 确保输出目录存在
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            print(f"  💾 正在保存 {len(self.all_jobs)} 条数据到: {output_file}")
            df = pd.DataFrame(self.all_jobs)
            df.to_excel(output_file, index=False, engine='openpyxl')
            print(f"  ✅ 已成功保存 {len(self.all_jobs)} 条数据到 {output_file}")
        except Exception as e:
            print(f"  ❌ Excel保存失败: {e}")
            import traceback
            traceback.print_exc()
            # 如果Excel保存失败，尝试保存为CSV
            try:
                csv_file = str(output_file).replace('.xlsx', '.csv')
                print(f"  💾 尝试保存为CSV格式: {csv_file}")
                df = pd.DataFrame(self.all_jobs)
                df.to_csv(csv_file, index=False, encoding='utf-8-sig')
                print(f"  ✅ 已成功保存为CSV格式: {csv_file}")
            except Exception as e2:
                print(f"  ❌ CSV保存也失败: {e2}")
                import traceback
                traceback.print_exc()


def configure_stdio_utf8_line_buffered() -> None:
    """
    Windows 下若用 TextIOWrapper 包一层 stdout 且未设行缓冲，print 会整段缓冲，进程结束时才刷到控制台。
    使用 line_buffering + write_through，使日志随运行即时可见。
    """
    import io
    import sys
    if sys.platform != "win32":
        return
    try:
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
                write_through=True,
            )
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
                write_through=True,
            )
    except Exception:
        pass


def main():
    """主函数"""
    configure_stdio_utf8_line_buffered()
    
    print("="*60)
    print("Boss直聘ICT招聘数据爬虫（全国搜索）")
    print("="*60)
    
    # 创建爬虫实例
    crawler = BossZhipinCrawler(
        wait_login=True,
        # False=监听 joblist API（已修复首屏监听与 /jobs URL）；True=点击侧栏取详情，较慢
        use_click_mode=False,
    )
    
    # 开始爬取
    crawler.crawl_all_ict_jobs(
        max_pages_per_keyword=10  # 每个关键词爬取10页
    )


if __name__ == "__main__":
    main()
