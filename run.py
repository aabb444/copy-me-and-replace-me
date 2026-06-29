import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# 强制清除所有缓存
import importlib
for mod in list(sys.modules.keys()):
    if any(x in mod for x in ['app', 'storage', 'rag', 'agent', 'note_task_agent']):
        del sys.modules[mod]

# 清理 .pyc 缓存
import shutil
for d in Path(__file__).parent.rglob("__pycache__"):
    shutil.rmtree(d, ignore_errors=True)

os.environ['FLASK_ENV'] = 'production'
os.environ['FLASK_DEBUG'] = '0'

# 读取 API Key
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text("utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.strip().split("=", 1)
                if k == "ANTHROPIC_API_KEY" and v:
                    api_key = v
                    os.environ["ANTHROPIC_API_KEY"] = v

# 导入应用
from app import app
from werkzeug.serving import run_simple

print("=== 启动服务: http://localhost:5001 ===")
run_simple("0.0.0.0", 5001, app, use_reloader=False, use_debugger=False, threaded=True)
