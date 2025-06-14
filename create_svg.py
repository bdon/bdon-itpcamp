import rasterio
import rasterio.mask
import fiona
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds, transform_geom
from rasterio.io import MemoryFile
from shapely.geometry import shape
from rasterio.transform import Affine
from rasterio.enums import Resampling
import base64
import xml.etree.ElementTree as ET
from shapely.affinity import affine_transform
from shapely import buffer
import numpy as np

TIFF_URL = "m_4007317_sw_18_060_20220719.tif"

DPI = 600

x_fudge = 10
y_fudge = 0.2

wgs_bounds = (-73.991339,40.678184,-73.986517,40.696261)

def format_coord(x):
    return f"{int(x)}" if x == int(x) else f"{x}"

def linestring_to_svg_path(linestring):
    coords = list(linestring.coords)
    if not coords:
        return ""
    d = [f"M {format_coord(coords[0][0])} {format_coord(coords[0][1])}"]
    d.extend(f"L {format_coord(x)} {format_coord(y)}" for x, y in coords[1:])
    return " ".join(d)

def rgb_to_grayscale_stretch_np(rgba: np.ndarray) -> np.ndarray:
  r, g, b, a = rgba
  gray = ((0.2989 * r + 0.5870 * g + 0.1140 * b) / 4).astype(r.dtype)
  return np.stack([gray, a]) 


raster = rasterio.open(TIFF_URL)
park_shape = fiona.open("prospectpark.geojson", "r")

# project the shape into the raster CRS
transformed_geom = shape(transform_geom(
  src_crs=park_shape.crs,
  dst_crs=raster.crs,
  geom=park_shape[0].geometry
))

# get the bounding box of the shape
bounds = rasterio.features.bounds(transformed_geom)
window = from_bounds(*bounds, transform=raster.transform)
print(bounds)
print(window)
transform = raster.window_transform(window)


p = raster.profile.copy()
p['count'] = 1

tmp_white = MemoryFile().open(**p)
white_band = np.full(raster.shape, 255, dtype='uint8')
tmp_white.write(white_band,1)

out_image, out_transform = rasterio.mask.mask(tmp_white, [transformed_geom], crop=True)
square_inches = np.count_nonzero(out_image) / (600 * 600)
print("square inches", square_inches)

scale_factor = 5 / square_inches
print("scale factor", scale_factor)

# resize the raster to be:
# 2 square inches at 600 DPI
print(window)
data = raster.read(window=window, out_shape = (raster.count, int(window.height * scale_factor), int(window.width * scale_factor)), resampling=Resampling.lanczos)

# it is now the correct size

# convert to NDVI
r,g,b,i = data

red = r.astype(np.float32)
nir = i.astype(np.float32)
numerator = nir - red
denominator = nir + red
ndvi = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator != 0)
ndvi_scaled = ((ndvi + 1) / 2 * 255).astype(np.uint8)


# tmp_white2 = MemoryFile().open(**p)
# print(data.shape)
# white_band2 = np.full((1,data.shape[1],data.shape[2]), 255, dtype='uint8')
# tmp_white2.write(white_band2,1)
# print(tmp_white2)

out_image, out_transform = rasterio.mask.mask(tmp_white, [transformed_geom], crop=True)


png = MemoryFile() 
with png.open(driver="PNG",width=data.shape[2],height=data.shape[1],count=1,dtype=np.uint8) as dst:
  dst.write(np.stack([ndvi_scaled]))

encoded_image = base64.b64encode(png.read()).decode("utf-8")


# write the svg
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

svg = ET.Element("svg", {
    "width": "24in",
    "height": "12in",
    "viewBox": "0 0 14400 7200",
    "version": "1.1",
    "xmlns": "http://www.w3.org/2000/svg",
})

group = ET.SubElement(svg, "g", {
  "transform": f"translate({x_fudge * DPI},{y_fudge * DPI})"
})

xformed = affine_transform(transformed_geom, (~out_transform).to_shapely())
xformed = affine_transform(xformed, Affine.scale(scale_factor).to_shapely())

cutline = buffer(xformed, 50)

ET.SubElement(group, "path", {
    "d": linestring_to_svg_path(cutline.exterior),
    "stroke": "red",
    "fill": "none",
    "stroke-width": "0.001pt"
})

ET.SubElement(group, "path", {
    "d": linestring_to_svg_path(xformed.exterior),
    "fill": "black",
})

ET.SubElement(group, "image", {
    "width": str(data.shape[2]),
    "height": str(data.shape[1]),
    "{http://www.w3.org/1999/xlink}href": f"data:image/png;base64,{encoded_image}"
})

tree = ET.ElementTree(svg)
tree.write("output.svg", encoding="UTF-8", xml_declaration=True)

# stretched = rgb_to_grayscale_stretch_np(out_image)

