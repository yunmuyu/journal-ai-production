from PIL import Image
from raster.render import compose


def test_column_fit_equal_width_without_blank_cells():
    images=[Image.new('L',(100,200),0),Image.new('L',(50,50),128)]
    result,positions=compose(images,{'mode':'column-fit','gap_px':0})
    assert result.size==(50,150)
    assert positions==[[0,0,50,100],[0,100,50,150]]
    assert result.getpixel((25,120))==128
