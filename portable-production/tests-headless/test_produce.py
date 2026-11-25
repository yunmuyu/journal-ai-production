import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from headless.produce import produce


def test_raster_screenshot_lands_in_the_author_folder(tmp_path):
    issue = tmp_path / 'issue'
    author = issue / '张三'
    author.mkdir(parents=True)
    Image.new('RGB', (30, 20), (180, 20, 40)).save(author / '张三-图1.png')
    report = produce(issue)
    delivered = author / '张三-图1.jpg'
    assert delivered.is_file()
    assert (author / '张三-图1.png').is_file()
    assert report['figures'][0]['status'] == 'delivered'
    assert report['figures'][0]['text_legibility_check'] is False
    with Image.open(delivered) as image:
        assert image.mode == 'L'


def test_web_page_hint_is_not_redrawn(tmp_path):
    issue = tmp_path / 'issue'
    author = issue / '李四'
    author.mkdir(parents=True)
    Image.new('RGB', (20, 20), (10, 20, 200)).save(author / '页面.png')
    job = tmp_path / 'job.json'
    job.write_text('{"figures":{"李四-图1":{"hint":"网页截图"}}}', encoding='utf-8')
    report = produce(issue, tmp_path / 'out', job)
    assert report['figures'][0]['route']['route'] == 'raster-only'
    assert report['figures'][0]['route']['redraw'] is False
