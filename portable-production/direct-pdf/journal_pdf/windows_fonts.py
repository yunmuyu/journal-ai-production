"""Explicit, one-shot setup helper. NEVER imported by render or batch."""
from pathlib import Path
import os
from .common import FigureError

def registry_inventory():
    if os.name!='nt':raise FigureError('windows_only','此命令只用于Windows首次配置；正常运行无需此命令')
    import winreg
    rows=[]
    keys=[(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts'),
          (winreg.HKEY_CURRENT_USER,r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts')]
    needles=('simsun','宋体','hya3','汉仪中宋','times new roman')
    for hive,keyname in keys:
        try:
            with winreg.OpenKey(hive,keyname) as key:
                for i in range(winreg.QueryInfoKey(key)[1]):
                    name,value,_=winreg.EnumValue(key,i)
                    if any(n.casefold() in name.casefold() for n in needles):
                        p=Path(os.path.expandvars(str(value)))
                        if not p.is_absolute():p=Path(os.environ['WINDIR'])/'Fonts'/p
                        rows.append({'registry_name':name,'path':str(p),'exists':p.is_file()})
        except FileNotFoundError:continue
    return {'one_time_registry_query':True,'font_directory_scans':0,'matches':rows,
            'note':'仅候选路径，不自动选择歧义字体；把确认后的路径写入fonts.local.json，之后不再调用此查询。'}
