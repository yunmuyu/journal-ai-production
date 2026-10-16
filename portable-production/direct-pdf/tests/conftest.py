import os,json
from pathlib import Path
import pytest
from journal_pdf.fonts import FontRegistry

@pytest.fixture(scope="session")
def profile():
    p=Path(os.environ.get("JFW_TEST_FONT_PROFILE",str(Path(__file__).resolve().parents[1]/"config/fonts.preview-linux.json")))
    if not p.is_file():pytest.skip("需要设置JFW_TEST_FONT_PROFILE为本机已配置的字体方案")
    data=json.loads(p.read_text())
    if any(not Path(v['path']).is_file() for v in data['faces'].values()):
        pytest.skip("当前测试字体路径不适用于本机，请显式指定字体方案；不扫描或自动替代")
    return p

@pytest.fixture
def reg(profile,tmp_path):
    f=FontRegistry(profile,tmp_path/'cache')
    try:yield f
    finally:f.close()

@pytest.fixture
def simple_spec():
    return {"version":1,"id":"synthetic-tree","author":"Synthetic","kind":"tree","synthetic":True,
            "root":"系统","branches":[{"text":"输入","children":["读取","校验"]},{"text":"输出","children":["PDF","记录"]}],
            "policy":{"column":"single","font_sizes":[8,7,6]}}
