import pymysql
from pymysql.err import OperationalError, ProgrammingError, InterfaceError

# MySQL 配置（直接复用你提供的配置）
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3306
MYSQL_USER = "root"
MYSQL_PASSWORD = "pf123456"
MYSQL_DATABASE = "zpsj"

def test_mysql_connection():
    """测试MySQL数据库连接"""
    conn = None
    try:
        # 建立数据库连接
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            charset="utf8mb4"  # 推荐使用utf8mb4，兼容所有Unicode字符（包括emoji）
        )
        print("✅ 数据库连接成功！")
        
        # 可选：简单验证数据库版本（确认连接有效）
        with conn.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
            print(f"📌 MySQL服务器版本：{version}")
            
    except OperationalError as e:
        # 处理连接相关错误（密码错误、主机不可达、端口错误、数据库不存在等）
        error_code, error_msg = e.args
        print(f"❌ 数据库连接失败：")
        print(f"   错误码：{error_code}")
        print(f"   错误信息：{error_msg}")
        if error_code == 1045:
            print("   提示：可能是用户名/密码错误")
        elif error_code == 1049:
            print("   提示：数据库 zpsj 不存在")
        elif error_code == 2003:
            print("   提示：MySQL服务未启动，或主机/端口错误")
    except ProgrammingError as e:
        print(f"❌ 数据库操作错误：{e}")
    except InterfaceError as e:
        print(f"❌ 数据库接口错误：{e}")
    except Exception as e:
        print(f"❌ 未知错误：{e}")
    finally:
        # 确保连接关闭，避免资源泄漏
        if conn:
            conn.close()
            print("🔌 数据库连接已关闭")

if __name__ == "__main__":
    test_mysql_connection()