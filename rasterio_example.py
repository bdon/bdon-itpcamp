import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds

# The original copy of the GeoTIFF.
# Because it is a COG, you can access parts without accessing the entire file
# see https://cogeo.org
TIFF_URL = "https://naipeuwest.blob.core.windows.net/naip/v002/ny/2022/ny_060cm_2022/40073/m_4007317_nw_18_060_20220719.tif"

# i determined these bounds by drawing in play.placemark.io and using "export BBOX"
# order is min_x, min_y, max_x, max_y
wgs_bounds = (-73.991339,40.6883,-73.97804,40.696261)

with rasterio.open(TIFF_URL) as src:

  # my defined bbox is in geographic coordinates, but we need to match the 
  # coordinate reference system (CRS) of the source raster
  bounds = transform_bounds("EPSG:4326", src.crs, *wgs_bounds, densify_pts=21)
  window = from_bounds(*bounds, transform=src.transform)
  transform = src.window_transform(window)

  # do the actual read operation of just the part we're interested in.
  data = src.read(window=window)

  # write the output GeoTIFF
  with rasterio.open(
        "out.tif", "w",
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        count=src.count,
        dtype=data.dtype,
        crs=src.crs,
        transform=transform
    ) as dst:
        dst.write(data)