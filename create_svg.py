import rasterio
import rasterio.mask
import fiona
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds, transform_geom
from rasterio.io import MemoryFile
from shapely.geometry import shape
from rasterio.transform import Affine
import base64
import xml.etree.ElementTree as ET
from shapely.affinity import affine_transform
from shapely import buffer
import numpy as np

TIFF_URL = "m_4007317_sw_18_060_20220719.tif"

DPI = 600

x_fudge = 5.5
y_fudge = 0.5

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

with rasterio.open(TIFF_URL) as src:

  # open the source clipping path
  with fiona.open("prospectpark.geojson", "r") as shap:
    transformed_geom = transform_geom(
      src_crs=shap.crs,
      dst_crs=src.crs,
      geom=shap[0].geometry
    )

    # transform it to the Shapely type
    poly = shape(transformed_geom)

    # adjust this to account for the target "right keychain size"
    FACTOR = 0.3
    scaling = Affine.scale(FACTOR, FACTOR)

    # get the bounding box of the shape
    bounds = rasterio.features.bounds(transformed_geom)
    window = from_bounds(*bounds, transform=src.transform)
    transform = src.window_transform(window)
    out_image, out_transform = rasterio.mask.mask(src, [poly], crop=True)


    xformed = affine_transform(poly, (~out_transform).to_shapely())

    xformed = affine_transform(xformed, scaling.to_shapely())

    xformed = buffer(xformed, 50)

    # data = src.read(window=window)

    stretched = rgb_to_grayscale_stretch_np(out_image)
    with MemoryFile() as memfile:
      with memfile.open(
            driver="PNG",
            width=stretched.shape[2],
            height=stretched.shape[1],
            count=stretched.shape[0],
            dtype=stretched.dtype,
            crs=src.crs,
            transform=transform * scaling
        ) as dst:
            dst.write(stretched)
      encoded_image = base64.b64encode(memfile.read()).decode("utf-8")

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

      cut_path = ET.SubElement(group, "path", {
        "d": linestring_to_svg_path(xformed.exterior),
        "stroke": "red",
        "fill": "none",
        "stroke-width": "0.001 pt"
      })

      image = ET.SubElement(group, "image", {
          "width": str(int(stretched.shape[2] * FACTOR)),
          "height": str(int(stretched.shape[1] * FACTOR)),
          "{http://www.w3.org/1999/xlink}href": f"data:image/png;base64,{encoded_image}"
      })

      tree = ET.ElementTree(svg)
      tree.write("output.svg", encoding="UTF-8", xml_declaration=True)