import rasterio
import rasterio.mask
import fiona
from rasterio.windows import from_bounds
from rasterio.transform import Affine
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.warp import transform_geom
from shapely.geometry import shape, mapping
from shapely.affinity import affine_transform
from shapely import buffer
import numpy as np
import base64
import xml.etree.ElementTree as ET
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

TEXT = "PROSPECT PARK"
FONT_PATH = "NationalPark-ExtraBold.otf"  # Replace with your .ttf path
FONT_SIZE = 72  # points

# Load font and get glyphs
font = TTFont(FONT_PATH)
glyph_set = font.getGlyphSet()
units_per_em = font["head"].unitsPerEm
scale = FONT_SIZE / units_per_em
cmap = font.getBestCmap()

TIFF_URL = "m_4007317_sw_18_060_20220719.tif"
GEOJSON_PATH = "prospectpark.geojson"
DPI = 600
x_fudge = 7
y_fudge = 4

def format_coord(x):
    return f"{int(x)}" if x == int(x) else f"{x}"

def linestring_to_svg_path(linestring):
    coords = list(linestring.coords)
    if not coords:
        return ""
    d = [f"M {format_coord(coords[0][0])} {format_coord(coords[0][1])}"]
    d.extend(f"L {format_coord(x)} {format_coord(y)}" for x, y in coords[1:])
    return " ".join(d)

# Open raster and vector
raster = rasterio.open(TIFF_URL)
park_shape = fiona.open(GEOJSON_PATH, "r")
shape_geom = shape(park_shape[0]['geometry'])

# Project shape to raster CRS
transformed_geom = shape(transform_geom(park_shape.crs, raster.crs, mapping(shape_geom)))

# Get bounding box and window from shape
bounds = rasterio.features.bounds(transformed_geom)
window = from_bounds(*bounds, transform=raster.transform)
window_transform = raster.window_transform(window)

# Create a mask raster to estimate area in square inches
profile = raster.profile.copy()
profile.update(count=1)
tmp_white = MemoryFile().open(**profile)
tmp_white.write(np.full(raster.shape, 255, dtype=np.uint8), 1)

out_image, _ = rasterio.mask.mask(tmp_white, [transformed_geom], crop=True)
square_inches = np.count_nonzero(out_image) / (DPI * DPI)
scale_factor = 5 / square_inches  # Targeting 5 square inches

# Rescale the raster
out_height = int(window.height * scale_factor)
out_width = int(window.width * scale_factor)
data = raster.read(window=window, out_shape=(raster.count, out_height, out_width), resampling=Resampling.lanczos)

# Compute new transform after scaling
scale_x = window.width / out_width
scale_y = window.height / out_height
new_transform = window_transform * Affine.scale(scale_x, scale_y)

# Compute NDVI
r, g, b, i = data
red = r.astype(np.float32)
nir = i.astype(np.float32)
numerator = nir - red
denominator = nir + red
ndvi = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator != 0)
ndvi_scaled = ((ndvi + 1) / 2 * 255).astype(np.uint8)

# Apply NDVI threshold
threshold = 0.4  # Adjust as needed (range is -1 to 1)

# Create mask where NDVI exceeds threshold
ndvi_mask = ndvi > threshold


# Create alpha mask based on transformed shape
tmp_white2 = MemoryFile().open(
    width=out_width,
    height=out_height,
    driver="GTiff",
    count=1,
    dtype=np.uint8,
    crs=profile['crs'],
    transform=new_transform
)
tmp_white2.write(np.full((out_height, out_width), 255, dtype=np.uint8), 1)

alpha, _ = rasterio.mask.mask(tmp_white2, [transformed_geom], crop=True)

shapefile_mask = alpha[0] > 0  # Shape-based mask (from rasterio.mask)
ndvi_mask = ndvi > threshold   # NDVI-based mask

# Combine: only pixels that are both in the shapefile and above NDVI threshold
combined_mask = shapefile_mask & ndvi_mask

# Final bands
grayscale_band = np.where(combined_mask, 255-32, 0).astype(np.uint8)
alpha_band = np.where(combined_mask, 255, 0).astype(np.uint8)

png = MemoryFile()
with png.open(driver="PNG", width=out_width, height=out_height, count=2, dtype=np.uint8) as dst:
    dst.write(grayscale_band, 1)
    dst.write(alpha_band, 2)

encoded_image = base64.b64encode(png.read()).decode("utf-8")

# Inverse transform for placing vector geometry in pixel space
inv_transform = ~new_transform
vector_pixels = affine_transform(transformed_geom, inv_transform.to_shapely())
cutline = buffer(vector_pixels, 50)

# SVG output
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

# Add cutline path
ET.SubElement(group, "path", {
    "d": linestring_to_svg_path(cutline.exterior),
    "stroke": "red",
    "fill": "none",
    "stroke-width": "0.001pt"
})

# Add filled vector shape
ET.SubElement(group, "path", {
    "d": linestring_to_svg_path(vector_pixels.exterior),
    "fill": "#c0c0c0",
})

# Embed raster as PNG image
ET.SubElement(group, "image", {
    "width": str(out_width),
    "height": str(out_height),
    "{http://www.w3.org/1999/xlink}href": f"data:image/png;base64,{encoded_image}"
})

labelgroup = ET.SubElement(group, "g", {
    "transform": f"translate(80,540) scale(0.06,-0.06)"
})

x_cursor = 0
hmtx = font["hmtx"]
for char in TEXT:
    if char == " ":
        x_cursor += hmtx["space"][0]  # advanceWidth
        continue
    glyph_name = cmap.get(ord(char))
    if not glyph_name:
        continue
    glyph = glyph_set[glyph_name]
    pen = SVGPathPen(glyph_set)
    glyph.draw(pen)
    path_data = pen.getCommands()

    # Add path to SVG
    ET.SubElement(labelgroup, "path", {
        "d": path_data,
        "fill": "white",
        "transform": f"translate({x_cursor},0)"
    })

    # Advance cursor
    advance_width = hmtx[glyph_name][0]
    x_cursor += advance_width


# Write SVG to file
tree = ET.ElementTree(svg)
tree.write("output.svg", encoding="UTF-8", xml_declaration=True)