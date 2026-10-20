from __future__ import annotations

import hashlib
from io import BytesIO

from .common import FigureError


def native_gray(data: bytes, *, allow_image_xobjects: bool=False) -> tuple[bytes, list]:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, ContentStream, FloatObject, NameObject

    writer=PdfWriter(clone_from=PdfReader(BytesIO(data)))
    proof=[]
    def gray(values):
        if len(values)!=3 or any(not 0<=float(v)<=1 for v in values):
            raise FigureError('source_glyph_color','仅验证三分量DeviceRGB值')
        luminance=sum(float(v)*w for v,w in zip(values,(.299,.587,.114),strict=True))
        return ArrayObject([FloatObject(luminance)]*3)
    for page in writer.pages:
        resources=page['/Resources']
        if resources.get('/XObject') and (not allow_image_xobjects or any(reference.get_object().get('/Subtype')!='/Image' for reference in resources['/XObject'].values())):
            raise FigureError('source_glyph_color','纯矢量选择后仍有XObject资源')
        for name,reference in resources.get('/Pattern',{}).items():
            pattern=reference.get_object();shading=pattern.get('/Shading',{})
            if pattern.get('/PatternType')!=2 or shading.get('/ColorSpace')!='/DeviceRGB' or shading.get('/ShadingType') not in (2,3):
                raise FigureError('source_glyph_pattern','仅验证原RGB轴向/径向梯度')
            function=shading['/Function']
            match function.get('/FunctionType'):
                case 0:
                    size=function.get('/Size');samples=function.get_data()
                    if not isinstance(size,list) or len(size)!=1 or function.get('/BitsPerSample')!=8 or function.get('/Order',1)!=1 or list(function.get('/Decode',[]))!=[0,1,0,1,0,1] or list(function.get('/Range',[]))!=[0,1,0,1,0,1] or list(function.get('/Domain',[]))!=[0,1] or list(function.get('/Encode',[]))!=[0,size[0]-1] or len(samples)!=int(size[0])*3:
                        raise FigureError('source_glyph_sampled_function','仅验证原一维8bit RGB线性采样表')
                    converted=bytes(component for i in range(0,len(samples),3) for component in [round(.299*samples[i]+.587*samples[i+1]+.114*samples[i+2])]*3)
                    function.set_data(converted)
                    proof.append({'pattern':str(name),'function_type':0,'sample_count':int(size[0]),'original_sample_sha256':hashlib.sha256(samples).hexdigest(),'gray_sample_sha256':hashlib.sha256(converted).hexdigest(),'sample_positions_and_function_parameters_unchanged':True})
                case 2:
                    if '/C0' not in function or '/C1' not in function:
                        raise FigureError('source_glyph_pattern','RGB指数梯度缺少端点')
                    function[NameObject('/C0')]=gray(function['/C0']);function[NameObject('/C1')]=gray(function['/C1'])
                    proof.append({'pattern':str(name),'function_type':2,'only_endpoint_colors_changed':True})
                case _:
                    raise FigureError('source_glyph_pattern','未验证的原梯度函数')
        stream=ContentStream(page.get_contents(),writer)
        operations=[]
        for args,op in stream.operations:
            if op in (b'k',b'K',b'sc',b'SC'):
                raise FigureError('source_glyph_color','不猜测原非RGB颜色空间')
            if op in (b'cs',b'CS') and args[0] not in ('/Pattern','/DeviceRGB','/DeviceGray'):
                raise FigureError('source_glyph_color','未验证的原颜色空间')
            if op in (b'scn',b'SCN') and (len(args)!=1 or not str(args[0]).startswith('/')):
                raise FigureError('source_glyph_color','仅验证命名原Pattern选择')
            if op in (b'rg',b'RG'):args=list(gray(args))
            operations.append((args,op))
        stream.operations=operations;page.replace_contents(stream)
    output=BytesIO();writer.write(output)
    return output.getvalue(),proof
